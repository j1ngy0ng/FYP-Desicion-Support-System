import { FormEvent, useEffect, useRef, useState } from 'react'

import { api, Badge, Progress } from './shared'
import type { Explanation, StudyMetrics, StudyStatistic } from './types'

type StudyCase = {
  study_token: string; case_id: string; campaign_type: string; channels: string; intent: string;
  roi: number; conversion_rate: number; engagement_score: number; action: string;
  confidence: number; confidence_level: string;
  presentation: 'raw' | 'confidence_only' | 'structured' | 'terse' | 'structured_no_caveat';
  raw_explanation?: string; terse_features?: string[]; explanation?: Explanation;
}
type StudyCases = { participant_code: string; participant_group?: 'Marketing practitioner' | 'Non-practitioner'; completed: number; total: number; cases: StudyCase[] }
type StudySummary = { overall: StudyMetrics; conditions: Record<string, StudyMetrics> }

const ratingOptions = [1, 2, 3, 4, 5]
const ratingLabels = ['Strongly disagree', 'Disagree', 'Neutral', 'Agree', 'Strongly agree']

function Rating({ name, label }: { name: string; label: string }) {
  return <div className="field"><label>{label}</label><select name={name} defaultValue="3" required>{ratingOptions.map(value => <option key={value} value={value}>{value} · {ratingLabels[value - 1]}</option>)}</select></div>
}

export function HumanStudy({ toast }: { toast: (message: string) => void }) {
  const [participant, setParticipant] = useState(() => sessionStorage.getItem('study-participant') || '')
  const [participantGroup, setParticipantGroup] = useState<'Marketing practitioner' | 'Non-practitioner'>('Marketing practitioner')
  const [study, setStudy] = useState<StudyCases>(); const [summary, setSummary] = useState<StudySummary>(); const [loading, setLoading] = useState(false)
  const current = study?.cases[0]
  const caseStarted = useRef(Date.now())
  useEffect(() => { caseStarted.current = Date.now() }, [current?.case_id])
  const refreshSummary = () => api<StudySummary>('/api/human-study/summary').then(setSummary).catch(error => toast(error.message))

  async function load(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true)
    try {
      const code = participant.trim().toUpperCase(); sessionStorage.setItem('study-participant', code); setParticipant(code)
      const loaded = await api<StudyCases>(`/api/human-study/cases?participant_code=${encodeURIComponent(code)}`)
      if (loaded.participant_group) setParticipantGroup(loaded.participant_group)
      setStudy(loaded)
      if (!loaded.cases.length) await refreshSummary()
    } catch (error) { toast((error as Error).message) } finally { setLoading(false) }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!current || !study) return
    const form = new FormData(event.currentTarget)
    try {
      await api('/api/human-study/responses', { method: 'POST', body: JSON.stringify({
        participant_code: study.participant_code, study_token: current.study_token,
        participant_group: participantGroup, actionability: Number(form.get('actionability')),
        specificity: Number(form.get('specificity')), feasibility: Number(form.get('feasibility')),
        explanation_usefulness: Number(form.get('explanation_usefulness')), reliance: Number(form.get('reliance')),
        willingness_to_review: Number(form.get('willingness_to_review')), user_acceptance: Number(form.get('user_acceptance')),
        decision: form.get('decision'), decision_time_ms: Date.now() - caseStarted.current,
        consent: form.get('consent') === 'on', comments: form.get('comments'),
      }) })
      setStudy({ ...study, completed: study.completed + 1, cases: study.cases.slice(1) }); await refreshSummary(); toast('Anonymous study response recorded.')
    } catch (error) { toast((error as Error).message) }
  }

  const overall = summary?.overall
  const statistic = (value: StudyStatistic, percent = false) => value.mean == null ? '—' : <>{percent ? `${(value.mean * 100).toFixed(1)}%` : value.mean.toFixed(2)}{value.ci95 && <><br /><span className="campaign-id">95% CI {percent ? `${(value.ci95[0] * 100).toFixed(1)}–${(value.ci95[1] * 100).toFixed(1)}%` : `${value.ci95[0].toFixed(2)}–${value.ci95[1].toFixed(2)}`}</span></>}</>
  return <section style={{ marginTop: 18 }}>
    <div className="card-head"><div><h2>Human-centred evaluation</h2><div className="card-note">This study unlocks only after the independent action-label audit and calibration stage. Use a pseudonymous participant code—never a name or email address.</div></div></div>
    {study && !current && <div className="grid grid-4">{[
      ['Responses', overall?.responses ?? 0, `${overall?.participants ?? 0} participants`],
      ['Actionability', overall?.actionability.mean?.toFixed(2) ?? '—', 'Mean rating / 5'],
      ['Trust alignment', overall?.trust_alignment.mean == null ? '—' : `${(overall.trust_alignment.mean * 100).toFixed(1)}%`, 'Higher is better'],
      ['Overtrust rate', overall?.overtrust_rate == null ? '—' : `${(overall.overtrust_rate * 100).toFixed(1)}%`, `${overall?.overtrust_cases ?? 0} eligible cases`],
    ].map(item => <article className="card metric-card" key={item[0]}><div className="metric-label">{item[0]}</div><div className="metric-value">{item[1]}</div><div className="trend">{item[2]}</div></article>)}</div>}
    {study && !current && summary && <div className="card" style={{ marginTop: 18 }}><div className="card-head"><div><h2>Blinded condition comparison</h2><div className="card-note">Condition identities are revealed only after this participant completes all cases.</div></div></div><div className="table-wrap"><table><thead><tr><th>Condition</th><th>Responses</th><th>Actionability ↑</th><th>Explanation usefulness ↑</th><th>Trust alignment ↑</th><th>Overtrust ↓</th><th>User acceptance ↑</th></tr></thead><tbody>{Object.entries(summary.conditions).map(([condition, values]) => <tr key={condition}><td><strong>{{ raw_uncalibrated: 'Raw explanation, uncalibrated', calibrated_confidence: 'Calibrated confidence only', structured_uncalibrated: 'Structured explanation, uncalibrated', terse_calibrated: 'Terse feature list', structured_calibrated: 'Driver–effect–action', full_framework: 'Driver–effect–action with confidence caveat' }[condition] || condition}</strong></td><td>{values.responses}<br /><span className="campaign-id">{values.participants} participants</span></td><td>{statistic(values.actionability)}</td><td>{statistic(values.explanation_usefulness)}</td><td>{statistic(values.trust_alignment, true)}</td><td>{values.overtrust_rate == null ? '—' : `${(values.overtrust_rate * 100).toFixed(1)}%`}</td><td>{statistic(values.user_acceptance)}</td></tr>)}</tbody></table></div></div>}
    <form className="card" style={{ marginTop: 18 }} onSubmit={load}><div className="form-grid"><div className="field"><label>Pseudonymous participant code</label><input value={participant} onChange={event => setParticipant(event.target.value)} minLength={3} maxLength={40} pattern="[A-Za-z0-9_-]+" placeholder="For example: P-001" required /></div><div className="field"><label>Participant group</label><select value={participantGroup} onChange={event => setParticipantGroup(event.target.value as typeof participantGroup)} disabled={Boolean(study?.completed)}><option>Marketing practitioner</option><option>Non-practitioner</option></select></div><div className="field"><label>Study progress</label><input value={study ? `${study.completed} of ${study.total} completed` : 'Enter a code to begin or resume'} disabled /></div></div><button className="btn btn-secondary" disabled={loading}>{loading ? 'Loading…' : study ? 'Reload study' : 'Start study'}</button></form>
    {study && !current && <div className="card empty-state" style={{ marginTop: 18 }}><strong>Study cases completed</strong>Thank you. This participant has evaluated all {study.total} frozen cases.</div>}
    {current && <><article className="card" style={{ marginTop: 18 }}><Progress label={`Case ${study.completed + 1} of ${study.total}`} value={(study.completed / study.total) * 100} /><div className="grid grid-3"><div><div className="metric-label">Campaign context</div><h3>{current.campaign_type}</h3><p className="card-note">{current.channels}</p></div><div><div className="metric-label">Strategic intent</div><p><Badge value={current.intent} /></p><p className="card-note">ROI {current.roi.toFixed(2)} · Conversion {(current.conversion_rate * 100).toFixed(1)}% · Engagement {current.engagement_score.toFixed(1)}</p></div><div><div className="metric-label">Recommendation</div><h2>{current.action}</h2><p className="card-note">{(current.confidence * 100).toFixed(1)}% confidence · {current.confidence_level}</p></div></div>{['structured', 'structured_no_caveat'].includes(current.presentation) && current.explanation && <><hr style={{ border: 0, borderTop: '1px solid var(--line)', margin: '20px 0' }} /><div className="grid grid-2"><div><h3>Driver and implication</h3><p>{current.explanation.driver}</p><p className="card-note">{current.explanation.implication}</p></div><div><h3>Recommended action{current.presentation === 'structured' ? ' and caveat' : ''}</h3><p>{current.explanation.action}</p>{current.presentation === 'structured' && <p className="card-note">{current.explanation.caveat}</p>}</div></div></>}{current.presentation === 'terse' && <><hr style={{ border: 0, borderTop: '1px solid var(--line)', margin: '20px 0' }} /><h3>Key features</h3><ul>{current.terse_features?.map(feature => <li key={feature}>{feature}</li>)}</ul></>}{current.presentation === 'raw' && <><hr style={{ border: 0, borderTop: '1px solid var(--line)', margin: '20px 0' }} /><p>{current.raw_explanation}</p></>}{current.presentation === 'confidence_only' && <p className="card-note">No explanatory text is shown for this neutral study condition.</p>}</article>
      <form className="card" style={{ marginTop: 18 }} onSubmit={submit}><div className="card-head"><div><h2>Evaluate this recommendation</h2><div className="card-note">1 = strongly disagree, 5 = strongly agree.</div></div></div><div className="form-grid"><Rating name="actionability" label="This recommendation provides a practical action I could apply." /><Rating name="specificity" label="The recommendation is specific enough to guide a marketing decision." /><Rating name="feasibility" label="The recommendation is feasible under the stated campaign context." /><Rating name="explanation_usefulness" label="The information shown clearly communicates the basis for the action." /><Rating name="reliance" label="I would act on this recommendation without additional evidence." /><Rating name="willingness_to_review" label="I would review supporting evidence before acting." /><Rating name="user_acceptance" label="I would use this system to support a marketing decision." /><div className="field full"><label>Managerial decision</label><select name="decision" defaultValue="Verify before accepting" required><option>Accept without checking</option><option>Verify before accepting</option><option>Modify before accepting</option><option>Reject</option></select></div><div className="field full"><label>Optional comments</label><textarea name="comments" rows={3} maxLength={1000} /></div><div className="field full"><label><input name="consent" type="checkbox" required style={{ width: 'auto' }} /> I have read the participant information and consent to this anonymous response being used for the FYP evaluation.</label></div></div><button className="btn btn-primary">Submit and continue</button></form></>}
  </section>
}
