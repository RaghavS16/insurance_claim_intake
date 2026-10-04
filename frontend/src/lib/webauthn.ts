export type WebAuthnPublicKey = Record<string, any>;

function base64UrlToBuffer(value: string): ArrayBuffer {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function bufferToBase64Url(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export function prepareCreationOptions(options: WebAuthnPublicKey): PublicKeyCredentialCreationOptions {
  return {
    ...options,
    challenge: base64UrlToBuffer(options.challenge),
    user: { ...options.user, id: base64UrlToBuffer(options.user.id) },
    excludeCredentials: (options.excludeCredentials || []).map((item: any) => ({
      ...item,
      id: base64UrlToBuffer(item.id),
    })),
  } as PublicKeyCredentialCreationOptions;
}

export function prepareRequestOptions(options: WebAuthnPublicKey): PublicKeyCredentialRequestOptions {
  return {
    ...options,
    challenge: base64UrlToBuffer(options.challenge),
    allowCredentials: (options.allowCredentials || []).map((item: any) => ({
      ...item,
      id: base64UrlToBuffer(item.id),
    })),
  };
}

export function serializeCredential(credential: PublicKeyCredential): Record<string, any> {
  const response = credential.response as AuthenticatorAttestationResponse | AuthenticatorAssertionResponse;
  const base: Record<string, any> = {
    id: credential.id,
    rawId: bufferToBase64Url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: bufferToBase64Url(response.clientDataJSON),
    },
  };

  if ("attestationObject" in response) {
    base.response.attestationObject = bufferToBase64Url(response.attestationObject);
    const transports = response.getTransports?.();
    if (transports?.length) base.response.transports = transports;
  } else {
    base.response.authenticatorData = bufferToBase64Url(response.authenticatorData);
    base.response.signature = bufferToBase64Url(response.signature);
    if (response.userHandle) base.response.userHandle = bufferToBase64Url(response.userHandle);
  }

  return base;
}

export function assertWebAuthnSupport(): void {
  if (typeof window === "undefined" || !window.PublicKeyCredential || !navigator.credentials) {
    throw new Error("This browser or device does not support passkeys.");
  }
}
