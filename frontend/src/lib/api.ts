export const api = {
  getProviders: () => request<Provider[]>("/api/providers"),
  getLanguages: () => request<Language[]>("/api/languages"),
  getFreeVoices: () => request<FreeVoice[]>("/api/free-voices"),
  getCookieStatus: () => request<CookieStatus>("/api/cookies/status"),
  createJob: (payload: JobCreatePayload) =>
    request<Job>("/api/jobs", { method: "POST", body: JSON.stringify(payload) }),
  listJobs: () => request<Job[]>("/api/jobs"),
  getJob: (id: string) => request<Job>(`/api/jobs/${id}`),
  retryJob: (id: string) => request<Job>(`/api/jobs/${id}/retry`, { method: "POST" }),
  submitMasks: (id: string, masks: MaskBox[]) =>
    request<Job>(`/api/jobs/${id}/masks`, { method: "POST", body: JSON.stringify({ masks }) }),
  submitLayout: (id: string, layout: TextLayoutZone[], enabled: boolean) =>
    request<Job>(`/api/jobs/${id}/layout`, { method: "POST", body: JSON.stringify({ layout, enabled }) }),
};
