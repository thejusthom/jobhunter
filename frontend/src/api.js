const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  getJobs: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/jobs${q ? '?' + q : ''}`);
  },
  getJob: (id) => request(`/jobs/${id}`),
  updateJob: (id, data) => request(`/jobs/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  getJobStats: () => request('/jobs/stats'),
  matchJob: (id) => request(`/jobs/${id}/match`, { method: 'POST' }),
  linkedinSearch: (id) => request(`/jobs/${id}/linkedin-search`),
  linkedinLeaders: (id, role = 'hiring') => request(`/jobs/${id}/linkedin-leaders?role=${role}`),
  findEmails: (id) => request(`/jobs/${id}/find-emails`),
  generateOutreach: (id, data = {}) => request(`/jobs/${id}/outreach`, { method: 'POST', body: JSON.stringify(data) }),
  getLinkedInId: (company) => request(`/linkedin-id?company=${encodeURIComponent(company)}`),
  updateLinkedInId: (company, linkedin_id) => request('/linkedin-id', { method: 'PATCH', body: JSON.stringify({ company, linkedin_id }) }),

  getApplications: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/applications${q ? '?' + q : ''}`);
  },
  getAppStats: () => request('/applications/stats'),
  createApplication: (data) => request('/applications', { method: 'POST', body: JSON.stringify(data) }),
  addApplicationByUrl: (url) => request('/applications/add-by-url', { method: 'POST', body: JSON.stringify({ url }) }),
  updateApplication: (id, data) => request(`/applications/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  getRecruiters: (appId) => request(`/recruiters${appId ? '?application_id=' + appId : ''}`),
  createRecruiter: (data) => request('/recruiters', { method: 'POST', body: JSON.stringify(data) }),

  getReminders: (all) => request(`/reminders${all ? '?include_completed=true' : ''}`),
  getDueReminders: () => request('/reminders/due'),
  createReminder: (data) => request('/reminders', { method: 'POST', body: JSON.stringify(data) }),
  completeReminder: (id) => request(`/reminders/${id}/complete`, { method: 'PATCH' }),

  getDashboard: () => request('/dashboard'),
  triggerDiscovery: (data = {}) => request('/discover', { method: 'POST', body: JSON.stringify(data) }),
  getDiscoveryStatus: () => request('/discover/status'),

  getEvaluations: (limit = 50) => request(`/evaluations?limit=${limit}`),
  getAnalytics: () => request('/analytics'),
  cleanupNonUs: () => request('/jobs/cleanup-non-us', { method: 'POST' }),
  getCollectedEmails: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return request(`/collected-emails${q ? '?' + q : ''}`);
  },

  clearQueue: () => request('/jobs/clear-queue', { method: 'POST' }),
  blockCompany: (company, reason = 'no sponsorship') => request('/blocked-companies', { method: 'POST', body: JSON.stringify({ company, reason }) }),
  getBlockedCompanies: () => request('/blocked-companies'),
  unblockCompany: (company) => request(`/blocked-companies/${encodeURIComponent(company)}`, { method: 'DELETE' }),
  addJobByUrl: (url) => request('/jobs/add-by-url', { method: 'POST', body: JSON.stringify({ url }) }),
  fixWorkdayUrls: () => request('/jobs/fix-workday-urls', { method: 'POST' }),

  // Auto-Apply Engine
  autoApplyStart: (data = {}) => request('/auto-apply/start', { method: 'POST', body: JSON.stringify(data) }),
  autoApplyStatus: () => request('/auto-apply/status'),
  autoApplyStop: () => request('/auto-apply/stop', { method: 'POST' }),
  autoApplyAction: (action) => request('/auto-apply/action', { method: 'POST', body: JSON.stringify({ action }) }),
};
