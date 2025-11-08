import React, { useEffect, useMemo, useState } from 'react'
import { ingest, jobs, jobStream, getSettings, saveSettings, pingIntegrations, triggerN8n, cancelJob, telegramNotify } from './api.js'

function JobRow({ item, onWatch, onTrigger, onCancel }) {
  return (
    <tr>
      <td style={{fontFamily:'monospace'}}>{item.job_id}</td>
      <td>{item.status}</td>
      <td>{item.enqueued_at}</td>
      <td>{item.started_at || '-'}</td>
      <td>{item.ended_at || '-'}</td>
      <td>
        <button onClick={() => onWatch(item.job_id)}>İzle</button>{' '}
        <button onClick={() => onTrigger(item.job_id)}>n8n</button>{' '}
        <button onClick={() => onCancel(item.job_id)}>İptal</button>
      </td>
    </tr>
  )
}

export default function App() {
  const [videoUrl, setVideoUrl] = useState('')
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(false)
  const [current, setCurrent] = useState(null) // jobId
  const [events, setEvents] = useState([])
  const [es, setEs] = useState(null)
  const [tab, setTab] = useState('jobs')

  // settings
  const [settings, setSettings] = useState({
    enable_n8n: false,
    n8n_webhook_url: '',
    enable_telegram: false,
    telegram_bot_token: '',
    telegram_chat_id: '',
    auto_trigger_n8n_on_finish: false
  })
  const [ping, setPing] = useState({})
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [intervalMs, setIntervalMs] = useState(4000)

  async function refresh() {
    try {
      const data = await jobs()
      setList(data.items)
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    if (!autoRefresh) return
    const t = setInterval(refresh, intervalMs)
    return () => clearInterval(t)
  }, [autoRefresh, intervalMs])

  async function onIngest() {
    if (!videoUrl) return
    setLoading(true)
    try {
      const res = await ingest(videoUrl)
      setVideoUrl('')
      await refresh()
      setCurrent(res.job_id)
    } catch (e) {
      alert(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!current) return
    // cleanup existing stream
    if (es) es.close()
    const _events = []
    setEvents(_events)
    const stream = jobStream(current, (ev) => {
      _events.push(ev)
      setEvents([..._events])
      // Auto trigger n8n on finish (client-side logic)
      if (
        ev?.status === 'finished' &&
        settings?.enable_n8n &&
        settings?.auto_trigger_n8n_on_finish
      ) {
        triggerN8n(current).catch(console.error)
      }
    })
    setEs(stream)
    return () => stream && stream.close()
  }, [current])

  useEffect(() => {
    // always load settings on mount and when switching to settings tab
    getSettings().then(setSettings).catch(console.error)
  }, [tab])

  async function onSaveSettings() {
    try {
      await saveSettings(settings)
      alert('Ayarlar kaydedildi')
    } catch (e) {
      alert(e.message)
    }
  }

  async function onPing() {
    try {
      const res = await pingIntegrations()
      setPing(res)
    } catch (e) {
      alert(e.message)
    }
  }

  async function onTrigger(jobId) {
    try {
      const res = await triggerN8n(jobId)
      alert(`n8n: ${res.ok ? 'OK' : 'HATA'} (${res.status_code})`)
    } catch (e) {
      alert(e.message)
    }
  }

  async function onCancel(jobId) {
    try {
      await cancelJob(jobId)
      refresh()
    } catch (e) {
      alert(e.message)
    }
  }

  async function onTelegramTest() {
    const msg = prompt('Gönderilecek mesaj:','Test mesajı')
    if (!msg) return
    try {
      await telegramNotify(msg)
      alert('Telegram gönderildi')
    } catch (e) {
      alert(e.message)
    }
  }

  return (
    <div className="container">
      <h1>Agents Admin (GitHub Pages Uyumlu)</h1>
      <p className="small" style={{color:'#fbbf24'}}>Sadece sahip olduğun / izinli içerikleri işle. YouTube ToS ve telif yasalarına uy.</p>

      <div className="tabs">
        <button className={`btn ${tab==='jobs'?'active':''}`} onClick={()=>setTab('jobs')} disabled={tab==='jobs'}>İşler</button>
        <button className={`btn ${tab==='settings'?'active':''}`} onClick={()=>setTab('settings')} disabled={tab==='settings'}>Ayarlar</button>
        <button className={`btn ${tab==='integrations'?'active':''}`} onClick={()=>setTab('integrations')} disabled={tab==='integrations'}>Entegrasyonlar</button>
      </div>

      {tab==='jobs' && (
        <>
          <div className="card" style={{display:'grid', gridTemplateColumns:'1fr auto', gap:8, alignItems:'center', margin:'12px 0'}}>
            <input className="input" placeholder="YouTube URL" value={videoUrl} onChange={e=>setVideoUrl(e.target.value)} />
            <button className="btn" onClick={onIngest} disabled={loading}>{loading ? 'Gönderiliyor...' : 'İçe Al'}</button>
          </div>

          <div className="row" style={{justifyContent:'space-between', margin:'8px 0'}}>
            <div className="row">
              <label className="row"><input type="checkbox" checked={autoRefresh} onChange={e=>setAutoRefresh(e.target.checked)} /> Otomatik yenile</label>
              <select className="input" value={intervalMs} onChange={e=>setIntervalMs(parseInt(e.target.value))}>
                <option value={2000}>2s</option>
                <option value={4000}>4s</option>
                <option value={8000}>8s</option>
              </select>
              <button className="btn" onClick={refresh}>Şimdi Yenile</button>
            </div>
          </div>

          <h2>İşler</h2>
          <table className="table">
            <thead>
              <tr style={{textAlign:'left', borderBottom:'1px solid #ddd'}}>
                <th>Job ID</th>
                <th>Durum</th>
                <th>Enqueue</th>
                <th>Start</th>
                <th>End</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {list.map(item => <JobRow key={item.job_id} item={item} onWatch={setCurrent} onTrigger={onTrigger} onCancel={onCancel} />)}
            </tbody>
          </table>

          {current && (
            <div style={{marginTop:24}} className="card">
              <h2>Canlı Akış: {current}</h2>
              <pre className="log">
                {events.map((e,i)=> <div key={i}>{JSON.stringify(e)}</div>)}
              </pre>
              {events.find(e=>e?.result) && (
                <>
                  <h3>Sonuç</h3>
                  <pre className="log">{JSON.stringify(events.find(e=>e?.result)?.result, null, 2)}</pre>
                </>
              )}
            </div>
          )}
        </>
      )}

      {tab==='settings' && (
        <>
          <h2>Ayarlar</h2>
          <div className="card" style={{display:'grid', gridTemplateColumns:'220px 1fr', gap:8, alignItems:'center', maxWidth:800}}>
            <label>n8n aktif</label>
            <input type="checkbox" checked={settings.enable_n8n} onChange={e=>setSettings({...settings, enable_n8n: e.target.checked})} />
            <label>n8n Webhook URL</label>
            <input className="input" value={settings.n8n_webhook_url||''} onChange={e=>setSettings({...settings, n8n_webhook_url: e.target.value})} />

            <label>Telegram aktif</label>
            <input type="checkbox" checked={settings.enable_telegram} onChange={e=>setSettings({...settings, enable_telegram: e.target.checked})} />
            <label>Telegram Bot Token</label>
            <input className="input" value={settings.telegram_bot_token||''} onChange={e=>setSettings({...settings, telegram_bot_token: e.target.value})} />
            <label>Telegram Chat ID</label>
            <input className="input" value={settings.telegram_chat_id||''} onChange={e=>setSettings({...settings, telegram_chat_id: e.target.value})} />

            <label>Job bitince n8n tetikle</label>
            <input type="checkbox" checked={settings.auto_trigger_n8n_on_finish} onChange={e=>setSettings({...settings, auto_trigger_n8n_on_finish: e.target.checked})} />
          </div>
          <div style={{marginTop:12, display:'flex', gap:8}}>
            <button className="btn" onClick={onSaveSettings}>Kaydet</button>
            <button className="btn" onClick={onPing}>Bağlantıları Test Et</button>
            <button className="btn" onClick={onTelegramTest}>Telegram Test Gönder</button>
          </div>
          <pre className="log" style={{marginTop:12}}>{Object.keys(ping).length? JSON.stringify(ping,null,2): ''}</pre>
        </>
      )}

      {tab==='integrations' && (
        <>
          <h2>Entegrasyonlar</h2>
          <div className="card">
            <p>n8n üzerinden WhatsApp/Instagram/Email vb. bağlayıcıları kurup, bu panelden webhook tetikleyebilirsiniz. Üretimde anahtarları asla frontend’e sızdırmayın.</p>
          <ul>
            <li>n8n Webhook Trigger → Job tamamlandığında çağır</li>
            <li>Telegram → anlık bildirim (bu panelden test)</li>
            <li>WhatsApp/Instagram → n8n içinde resmi ya da üçüncü taraf düğümlerle</li>
          </ul>
            <p className="small">n8n lokal: http://localhost:5678</p>
          </div>
        </>
      )}
    </div>
  )
}
