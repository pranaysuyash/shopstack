import { api } from './client';
import type { TokenResponse, WhoAmI, RegisterRequest, LoginRequest } from './types';

export async function registerDevice(req: RegisterRequest): Promise<TokenResponse> {
  return api.post<TokenResponse>('/api/v1/auth/register', req, true);
}

export async function loginDevice(req: LoginRequest): Promise<TokenResponse> {
  return api.post<TokenResponse>('/api/v1/auth/login', req, true);
}

export async function refreshToken(token: string): Promise<TokenResponse> {
  return api.post<TokenResponse>('/api/v1/auth/refresh', { token }, true);
}

export async function logout(token: string, allDevices = false): Promise<{ revoked: number }> {
  return api.post<{ revoked: number }>('/api/v1/auth/logout', { token, all_devices: allDevices }, true);
}

export async function whoami(): Promise<WhoAmI> {
  return api.get<WhoAmI>('/api/v1/meta/whoami', undefined, true);
}
