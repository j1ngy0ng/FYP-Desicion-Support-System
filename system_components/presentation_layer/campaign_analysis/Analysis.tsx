import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'

import { api, Badge, go, PageHead, Progress, query } from '../web_app/src/shared'
import type { Campaign } from '../web_app/src/types'

type AnalysisResult = {
  performance_score: number
  channel_attribution: { channel: string; contribution: number }[]
  attribution: { feature: string; contribution: number }[]
}

export function Analysis({ campaigns, toast }: { campaigns: Campaign[]; toast: (message: string) => void }) {
  const campaign = campaigns.find(c => c.id === query().get('id')) || campaigns[0]
  const [result, setResult] = useState<AnalysisResult>()
  useEffect(() => { if (campaign) api<AnalysisResult>(`/api/campaigns/${campaign.id}/analysis`).then(setResult).catch(error => toast(error.message)) }, [campaign?.id])
  if (!campaign) return null
  const channels = result?.channel_attribution || []
  return <div className="page"><PageHead eyebrow="Predictive analytics" title={campaign.name} subtitle={`${campaign.id} · ${campaign.channel} · ${campaign.intent} intent`}><button className="btn btn-ghost" onClick={() => go('campaigns')}>All campaigns</button><button className="btn btn-primary" onClick={() => go(`generate?campaign=${campaign.id}`)}>Generate recommendation</button></PageHead>
    <section className="grid grid-4">{[['ROI', campaign.roi.toFixed(2), campaign.roi > 0 ? 'Healthy return' : 'Needs attention'], ['Conversion rate', `${campaign.conversion}%`, 'Observed campaign rate'], ['Engagement score', campaign.engagement_score.toFixed(1), 'Audience response'], ['Predictive outlook', `${Math.round((result?.performance_score || 0) * 100)}%`, 'Neural evidence score']].map(metric => <article className="card metric-card" key={metric[0]}><div className="metric-label">{metric[0]}</div><div className="metric-value">{metric[1]}</div><div className="trend">{metric[2]}</div></article>)}</section>
    <section className="grid grid-3" style={{ marginTop: 18 }}><article className="card span-2"><div className="card-head"><div><h2>Campaign-level channel evidence</h2><div className="card-note">Training-derived campaign-level channel evidence</div></div></div>{channels.map(item => <Progress key={item.channel} label={item.channel} value={item.contribution * 100} />)}</article><article className="card"><div className="card-head"><h2>Predictive outlook</h2></div><div className="score-ring" style={{ '--score': Math.round((result?.performance_score || 0) * 100), margin: 'auto' } as CSSProperties}><div><span><strong>{Math.round((result?.performance_score || 0) * 100)}</strong><small>performance</small></span></div></div><p className="card-note" style={{ textAlign: 'center' }}>Expected effectiveness based on the frozen benchmark model.</p></article></section>
    <section className="card" style={{ marginTop: 18 }}><div className="card-head"><div><h2>Key performance drivers</h2><div className="card-note">Input-gradient factors with the strongest estimated influence</div></div></div><div className="grid grid-3">{(result?.attribution || []).slice(0, 3).map(item => <div key={item.feature}><Badge value="Performance" /><h3 style={{ marginTop: 10 }}>{item.feature.replaceAll('_', ' ')}</h3><p className="card-note">Relative sensitivity: {(item.contribution * 100).toFixed(1)}%</p></div>)}</div></section>
  </div>
}
