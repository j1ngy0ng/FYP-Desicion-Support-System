import { FormEvent, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'

import { api, Badge, go, PageHead, Progress, query } from '../web_app/src/shared'
import type { Recommendation } from '../web_app/src/types'

export function RecommendationDetails({ current, recommendations, setCurrent, reload, toast }: { current?: Recommendation; recommendations: Recommendation[]; setCurrent: (recommendation: Recommendation) => void; reload: () => void; toast: (message: string) => void }) {
  const id = Number(query().get('id'))
  const [feedbackRecorded, setFeedbackRecorded] = useState(false)
  const recommendation = (id ? (current?.numeric_id === id ? current : recommendations.find(item => item.numeric_id === id)) : current) || recommendations[0]
  useEffect(() => { if (id && recommendation?.rules === undefined) api<Recommendation>(`/api/recommendations/${id}`).then(setCurrent).catch(error => toast(error.message)) }, [id, recommendation?.rules])
  if (!recommendation) return <div className="page"><div className="empty-state"><strong>No recommendation selected</strong>Generate a recommendation first.</div></div>
  async function decide(decision: string) {
    try {
      const updated = await api<Recommendation>(`/api/recommendations/${recommendation.numeric_id}/decision`, { method: 'PATCH', body: JSON.stringify({ decision }) })
      setCurrent(updated); await reload(); toast(`Recommendation ${decision.toLowerCase()}.`)
    } catch (error) { toast((error as Error).message) }
  }
  async function evaluate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget)
    try {
      await api(`/api/recommendations/${recommendation.numeric_id}/evaluations`, {
        method: 'POST',
        body: JSON.stringify({
          actionability: Number(form.get('actionability')),
          trust_alignment: Number(form.get('trust_alignment')),
          explanation_usefulness: Number(form.get('explanation_usefulness')),
          user_acceptance: Number(form.get('user_acceptance')),
          comments: form.get('comments'),
        }),
      })
      setFeedbackRecorded(true); toast('Recommendation feedback recorded.')
    } catch (error) { toast((error as Error).message) }
  }
  const icon = recommendation.action === 'Increase' ? '↗' : recommendation.action === 'Reduce' ? '↘' : recommendation.action === 'Investigate' ? '?' : '→'
  return <div className="page"><PageHead eyebrow={`Recommendation ${recommendation.id}`} title="Recommendation details" subtitle={`Generated for ${recommendation.campaign} using predictive and campaign-level channel evidence with weighted safeguard reasoning.`}><button className="btn btn-ghost" onClick={() => go('history')}>View history</button></PageHead>
    <article className="card recommendation-hero"><div className="action-orb">{icon}</div><div><Badge value="Recommended action" /><h1 style={{ fontSize: 38, marginTop: 8 }}>{recommendation.action}</h1><p className="subhead">{recommendation.explanation.action}</p></div><div className="score-ring" style={{ '--score': recommendation.confidence } as CSSProperties}><div><span><strong>{recommendation.confidence}%</strong><small>{recommendation.calibration_status === 'calibrated' ? 'calibrated confidence' : 'uncalibrated evidence'}</small></span></div></div></article>
    <section className="grid grid-2" style={{ marginTop: 18 }}><article className="card"><div className="card-head"><h2>Why this action?</h2></div><ul className="reason-list"><li><strong>Driver</strong><br /><span className="card-note">{recommendation.explanation.driver}</span></li><li><strong>Implication</strong><br /><span className="card-note">{recommendation.explanation.implication}</span></li><li><strong>Intent alignment</strong><br /><span className="card-note">{recommendation.explanation.intent}</span></li></ul></article><article className="card"><div className="card-head"><h2>Decision scores</h2></div>{recommendation.ranked_actions.map(item => <Progress key={item.action} label={item.action} value={item.score * 100} />)}</article></section>
    <section className="card" style={{ marginTop: 18 }}><div className="card-head"><div><h2>Activated rule evidence</h2><div className="card-note">Applicable rules for the selected action, including satisfied checks and triggered penalties.</div></div></div>{recommendation.rules?.length ? recommendation.rules.map((rule, index) => <div className="rule-row" key={`${rule.name}-${index}`}><div><strong>{rule.triggered ? 'Penalty triggered' : 'Rule satisfied'}</strong><div className="card-note">{rule.name}</div></div><Badge value={rule.triggered ? 'Review' : 'Active'} /><strong>{rule.score.toFixed(1)}</strong></div>) : <p className="card-note">No selected-action rule checks were applicable.</p>}</section>
    <section className="grid grid-2" style={{ marginTop: 18 }}><article className="card"><div className="card-head"><h2>Recommended next steps</h2></div><ol><li>{recommendation.explanation.action}</li><li>Review the strongest predictive feature and campaign-level channel signal.</li><li>Record the final managerial decision.</li><li>Monitor ROI and acquisition cost after action.</li></ol></article><article className="card"><div className="card-head"><h2>Caveats</h2></div><p>{recommendation.explanation.caveat}</p><div className="actions"><button className="btn btn-danger" onClick={() => decide('Rejected')}>Reject</button><button className="btn btn-ghost" onClick={() => decide('Deferred')}>Defer</button><button className="btn btn-primary" onClick={() => decide('Accepted')}>Accept recommendation</button></div></article></section>
    <form className="card" style={{ marginTop: 18 }} onSubmit={evaluate}><div className="card-head"><div><h2>Evaluate this recommendation</h2><div className="card-note">Record human feedback for audit and usability analysis. These ratings do not retrain the model.</div></div></div>{feedbackRecorded ? <p><strong>Feedback recorded.</strong> Thank you for reviewing this recommendation.</p> : <><div className="form-grid">{[['actionability', 'Actionability'], ['trust_alignment', 'Appropriate confidence'], ['explanation_usefulness', 'Explanation usefulness'], ['user_acceptance', 'Willingness to use']].map(([name, label]) => <div className="field" key={name}><label>{label} (1–5)</label><select name={name} defaultValue="3"><option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select></div>)}<div className="field full"><label>Optional comments</label><textarea name="comments" rows={3} maxLength={1000} /></div></div><button className="btn btn-secondary">Submit feedback</button></>}</form>
  </div>
}
