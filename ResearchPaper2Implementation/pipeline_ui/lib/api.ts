export const API_BASE =
  process.env.NEXT_PUBLIC_PIPELINE_API ?? 'http://127.0.0.1:8765';

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
  const payload = await response.json();
  if (!response.ok)
    throw new Error(
      typeof payload === 'object' && payload && 'error' in payload
        ? String(payload.error)
        : `Request failed (${response.status})`,
    );
  return payload as T;
}

export type Corpus = {
  id: string;
  name: string;
  description: string;
  nodePrefix: string;
  filePrefix: string;
  profile: string;
  profileExists: boolean;
  sourceExists: boolean;
  builtIn: boolean;
  artifacts: { raw: number; clean: number; verified: number };
  buildStatus: string;
  errors: string[];
};
export type ContextDetails = {
  target_provision?: string;
  norms_included?: number;
  provisions_included?: number;
  exceptions_included?: number;
  token_estimate?: number;
  inbound_provisions?: string[];
  outbound_provisions?: string[];
};
export type Run = {
  provision?: string;
  text?: string;
  queryContext?: string;
  feature?: string;
  prompt?: string;
  summary?: string;
  error?: string;
  warnings?: string[];
  details?: ContextDetails;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    usage_source?: string;
    [key: string]: unknown;
  };
  record?: Record<string, unknown>;
};
export type Job = {
  id: string;
  kind: string;
  label: string;
  status: string;
  createdAt: number;
  finishedAt?: number;
  stage?: string;
  progress?: { done: number; total: number };
  logs: string[];
  error?: string;
  request: Record<string, unknown>;
  command?: string;
  result?: {
    summary?: string;
    error?: string;
    warnings?: string[];
    provisions?: string[] | number;
    profile?: string;
    files?: string[];
    items?: Run[];
    runs?: Run[];
  };
};
