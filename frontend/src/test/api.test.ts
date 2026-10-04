import {beforeEach,describe,expect,it,vi} from 'vitest';
import {api} from '../api';

describe('api client',()=>{
  beforeEach(()=>{localStorage.clear();vi.restoreAllMocks();});
  it('adds the bearer token and parses successful JSON responses',async()=>{
    localStorage.setItem('access_token','token-123');
    const fetchMock=vi.spyOn(globalThis,'fetch').mockResolvedValue(new Response(JSON.stringify({ok:true}),{status:200,headers:{'Content-Type':'application/json'}}));
    await expect(api('/api/v1/example')).resolves.toEqual({ok:true});
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/v1/example',expect.objectContaining({headers:expect.any(Headers)}));
    const headers=(fetchMock.mock.calls[0][1] as RequestInit).headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer token-123');
  });
});