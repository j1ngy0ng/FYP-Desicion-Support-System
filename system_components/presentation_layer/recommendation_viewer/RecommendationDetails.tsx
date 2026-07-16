import { useEffect } from 'react'
import type { CSSProperties } from 'react'

import { api, Badge, go, PageHead, Progress, query } from '../web_app/src/shared'
import type { Recommendation } from '../web_app/src/types'

export function RecommendationDetails({ current, recommendations, setCurrent, reload, toast }: { current?: Recommendation; recommendations: Recommendation[]; setCurrent: (recommendation: Recommendation) => void; reload: () => void; toast: (message: string) => void }) {
  const id = Number(query().get('id'))
  const recommendation = (id ? recommendations.find(item => item.numeric_id === id) : current) || recommendations[0]
  useEffect(() => { if (id && (!recommendation || !recommendation.explanation)) api<Recommendation>(`/api/recommendations/${id}`).then(setCurrent).catch(error => toast(error.message)) }, [id])
  if (!recommendation) return <div className="page"><div className="empty-state"><strong>No recommendation selected</strong>Generate a recommendation first.</div></div>
  async function decide(decision: string) {
    try {
      const updated = await api<Recommendation>(`/api/recommendations/${recommendation.numeric_id}/decision`, { method: 'PATCH', body: JSON.stringify({ decision }) })
      setCurrent(updated); await reload(); toast(`Recommendation ${decision.toLowerCase()}.`)
    } catch (error) { toast((error as Error).message) }
  }
  const icon = recommendation.action === 'Increase' ? '↗' : recommendation.action === 'Decrease' ? '↘' : recommendation.action === 'Investigate' ? '?' : '→'
  return <div className="page"><PageHead eyebrow={`Recommendation ${recommendation.id}`} title="Recommendation details" subtitle={`Generated for ${recommendation.campaign} using predictive attribution and weighted soft-rule reasoning.`}><button className="btn btn-ghost" onClick={() => go('history')}>View history</button></PageHead>
    <article className="card recommendation-hero"><div className="action-orb">{icon}</div><div><Badge value="Recommended action" /><h1 style={{ fontSize: 38, marginTop: 8 }}>{recommendation.action}</h1><p className="subhead">{recommendation.explanation.action}</p></div><div className="score-ring" style={{ '--score': recommendation.confidence } as CSSProperties}><div><span><strong>{recommendation.confidence}%</strong><small>calibrated trust</small></span></div></div></article>
    <section className="grid grid-2" style={{ marginTop: 18 }}><article className="card"><div className="card-head"><h2>Why this action?</h2></div><ul className="reason-list"><li><strong>Driver</strong><br /><span className="card-note">{recommendation.explanation.driver}</span></li><li><strong>Implication</strong><br /><span className="card-note">{recommendation.explanation.implication}</span></li><li><strong>Intent alignment</strong><br /><span className="card-note">{recommendation.explanation.intent}</span></li></ul></article><article className="card"><div className="card-head"><h2>Decision scores</h2></div>{recommendation.ranked_actions.map(item => <Progress key={item.action} label={item.action} value={item.score * 100} />)}</article></section>
    <section className="grid grid-2" style={{ marginTop: 18 }}><article className="card"><div className="card-head"><h2>Recommended next steps</h2></div><ol><li>{recommendation.explanation.action}</li><li>Review the strongest attributed feature and channel.</li><li>Record the final managerial decision.</li><li>Monitor ROI and acquisition cost after action.</li></ol></article><article className="card"><div className="card-head"><h2>Caveats</h2></div><p>{recommendation.explanation.caveat}</p><div className="actions"><button className="btn btn-danger" onClick={() => decide('Rejected')}>Reject</button><button className="btn btn-ghost" onClick={() => decide('Deferred')}>Defer</button><button className="btn btn-primary" onClick={() => decide('Accepted')}>Accept recommendation</button></div></article></section>
  </div>
}
