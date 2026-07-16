import type { ReactNode } from 'react'

export const go = (route: string) => { location.hash = `#/${route}` }
export const query = () => new URLSearchParams(location.hash.split('?')[1] || '')

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = sessionStorage.getItem('ms-token')
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } })
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Request failed')
  return response.status === 204 ? undefined as T : response.json()
}

export function Badge({ value }: { value: string }) {
  const tone = ['Active', 'Accepted', 'Growth', 'Performance', 'Intent'].includes(value) ? '' : ['Review', 'Pending', 'Retention', 'Evidence', 'Cost'].includes(value) ? 'amber' : value === 'Rejected' ? 'red' : ['Survival', 'Channel'].includes(value) ? 'blue' : 'gray'
  return <span className={`badge ${tone}`}><span className="status-dot" />{value}</span>
}

export function PageHead({ eyebrow, title, subtitle, children }: { eyebrow: string; title: string; subtitle: string; children?: ReactNode }) {
  return <div className="page-head"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="subhead">{subtitle}</p></div>{children && <div className="actions">{children}</div>}</div>
}

export function Progress({ label, value }: { label: string; value: number }) {
  return <div style={{ margin: '17px 0' }}><div className="legend-row"><strong>{label}</strong><span>{value.toFixed(0)}%</span></div><div className="progress"><span style={{ width: `${Math.max(2, Math.min(value, 100))}%` }} /></div></div>
}
