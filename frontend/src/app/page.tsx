"use client";

import { useEffect, useState } from 'react';
import { ShieldCheck, Zap } from 'lucide-react';
import { useMarketData } from '@/hooks/useMarketData';
import { usePendingApprovals } from '@/hooks/usePendingApprovals';
import { API_URL } from '@/lib/api';

type Portfolio = {
  balances?: Record<string, number>;
  metrics?: { equity?: number; daily_pnl_pct?: number; drawdown_pct?: number };
  error?: string;
};

const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
const pct = (n: number) => `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`;

export default function Dashboard() {
  const { tickers, connected } = useMarketData();
  const { approvals, handleApproval } = usePendingApprovals();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);

  useEffect(() => {
    const fetchPortfolio = async () => {
      try {
        const res = await fetch(`${API_URL}/api/portfolio`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setPortfolio(await res.json());
        setPortfolioError(null);
      } catch {
        setPortfolioError(`The API is not reachable at ${API_URL}. Start it with: python app/api_server.py`);
      }
    };
    fetchPortfolio();
    const timer = setInterval(fetchPortfolio, 15000);
    return () => clearInterval(timer);
  }, []);

  // The API approves a proposal only with its confirm_token, which the agent received when it
  // placed the order; it re-runs the Risk Guardian before anything executes.
  const review = async (requestId: string) => {
    const token = window.prompt('Paste the confirm_token your agent received with this proposal to approve it:');
    if (!token) return;
    const ok = await handleApproval(requestId, token.trim(), true);
    window.alert(
      ok
        ? 'Approved: the trade was re-checked and sent.'
        : 'Not approved: the token was wrong, the proposal expired, or the Risk Guardian refused it on re-check.'
    );
  };

  const metrics = portfolio?.metrics;
  const balances = Object.entries(portfolio?.balances ?? {});

  return (
    <div className="dashboard-grid">
      {/* Portfolio */}
      <section className="col-span-2 card">
        <div className="card-header">
          <div>
            <h3>Portfolio</h3>
            <p className="muted">Paper account balances from the API</p>
          </div>
          {metrics?.equity !== undefined && (
            <div className="value-pnl">
              <h2>{usd(metrics.equity)}</h2>
              {metrics.daily_pnl_pct !== undefined && (
                <span className={metrics.daily_pnl_pct >= 0 ? 'success' : 'danger'}>{pct(metrics.daily_pnl_pct)} today</span>
              )}
            </div>
          )}
        </div>
        {portfolioError ? (
          <p className="muted">{portfolioError}</p>
        ) : portfolio?.error ? (
          <p className="muted">{portfolio.error}</p>
        ) : !portfolio ? (
          <p className="muted">Loading…</p>
        ) : balances.length === 0 ? (
          <p className="muted">No balances yet. Fund the paper account with deposit_paper_funds.</p>
        ) : (
          <div className="strategy-list">
            {balances.map(([asset, amount]) => (
              <div key={asset} className="strategy-item">
                <span>{asset}</span>
                <span>{amount.toLocaleString()}</span>
              </div>
            ))}
            {metrics?.drawdown_pct !== undefined && (
              <div className="strategy-item">
                <span className="muted">Drawdown from peak</span>
                <span>{(metrics.drawdown_pct * 100).toFixed(2)}%</span>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Real-time Ticker */}
      <section className="card">
        <div className="card-header">
          <h3>Live Markets</h3>
          <span className={`connection-dot ${connected ? 'online' : 'offline'}`}></span>
        </div>
        <div className="ticker-list">
          {Object.values(tickers).length === 0 ? (
            <p className="muted">Waiting for stream...</p>
          ) : (
            Object.values(tickers).map((t) => (
              <div key={t.symbol} className="ticker-item">
                <span className="symbol">{t.symbol}</span>
                <span className="price">${t.last.toLocaleString()}</span>
                <span className="source muted">{t.source}</span>
              </div>
            ))
          )}
        </div>
      </section>

      {/* Guard Rail / Pending Approvals */}
      <section className="card">
        <div className="card-header">
          <div className="icon-title">
            <ShieldCheck className="primary" size={20} />
            <h3>Guard Rail</h3>
          </div>
          {approvals.length > 0 && <span className="warning-badge">{approvals.length}</span>}
        </div>
        <div className="approval-list">
          {approvals.length === 0 ? (
            <div className="empty-approval">
              <Zap className="muted" size={32} />
              <p className="muted">No pending approvals</p>
            </div>
          ) : (
            approvals.map((a) => (
              <div key={a.request_id} className="approval-item">
                <div className="approval-info">
                  <span className="kind">{a.kind.replace('_', ' ')}</span>
                  <span className="muted">ID: {a.request_id.slice(0, 8)}...</span>
                </div>
                <button className="btn btn-primary compact" onClick={() => review(a.request_id)}>
                  Approve
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
