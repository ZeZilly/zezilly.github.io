const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function ingest(url) {
  const res = await fetch(`${API_BASE}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, confirm_rights: true })
  });
  if (!res.ok) throw new Error(`Ingest failed: ${res.status}`);
  return res.json();
}

export async function jobs(limit = 50) {
  const res = await fetch(`${API_BASE}/jobs?limit=${limit}`);
  if (!res.ok) throw new Error('Jobs fetch failed');
  return res.json();
}

export function jobStream(jobId, onEvent) {
  const es = new EventSource(`${API_BASE}/jobs/${jobId}/stream`);
  es.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      onEvent(data);
    } catch (e) {
      console.error('Bad SSE data', e);
    }
  };
  es.onerror = (e) => {
    console.warn('SSE error', e);
    es.close();
  };
  return es;
}

  export async function getSettings() {
    const res = await fetch(`${API_BASE}/admin/settings`)
    if (!res.ok) throw new Error('Settings fetch failed')
    return res.json()
  }

  export async function saveSettings(payload) {
    const res = await fetch(`${API_BASE}/admin/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!res.ok) throw new Error('Settings save failed')
    return res.json()
  }

  export async function pingIntegrations() {
    const res = await fetch(`${API_BASE}/integrations/ping`, { method: 'POST' })
    if (!res.ok) throw new Error('Ping failed')
    return res.json()
  }

  export async function triggerN8n(jobId) {
    const res = await fetch(`${API_BASE}/jobs/${jobId}/trigger/n8n`, { method: 'POST' })
    if (!res.ok) throw new Error('n8n trigger failed')
    return res.json()
  }

  export async function cancelJob(jobId) {
    const res = await fetch(`${API_BASE}/jobs/${jobId}/cancel`, { method: 'POST' })
    if (!res.ok) throw new Error('Cancel failed')
    return res.json()
  }

  export async function telegramNotify(message) {
    const res = await fetch(`${API_BASE}/notify/telegram`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    })
    if (!res.ok) throw new Error('Telegram notify failed')
    return res.json()
  }
