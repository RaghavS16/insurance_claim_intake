import { describe, expect, it } from "vitest";
import { prepareCreationOptions, prepareRequestOptions, serializeCredential } from "./webauthn";

const b64 = (value: Uint8Array) => Buffer.from(value).toString("base64url");

describe("WebAuthn serialization", () => {
  it("converts base64url challenges and credential IDs to ArrayBuffer", () => {
    const challenge = b64(new Uint8Array([1, 2, 3]));
    const userId = b64(new Uint8Array([4, 5, 6]));
    const options = prepareCreationOptions({ challenge, user: { id: userId, name: "user", displayName: "User" } });
    expect(new Uint8Array(options.challenge as ArrayBuffer)).toEqual(new Uint8Array([1, 2, 3]));
    expect(new Uint8Array(options.user.id as ArrayBuffer)).toEqual(new Uint8Array([4, 5, 6]));
  });

  it("prepares assertion options without mutating the original payload", () => {
    const challenge = b64(new Uint8Array([7, 8]));
    const id = b64(new Uint8Array([9, 10]));
    const source = { challenge, allowCredentials: [{ id, type: "public-key" }] };
    const prepared = prepareRequestOptions(source);
    expect(new Uint8Array(prepared.challenge as ArrayBuffer)).toEqual(new Uint8Array([7, 8]));
    expect(new Uint8Array(prepared.allowCredentials![0].id as ArrayBuffer)).toEqual(new Uint8Array([9, 10]));
    expect(source.challenge).toBe(challenge);
  });

  it("serializes assertion response fields as base64url", () => {
    const buffer = new Uint8Array([11, 12]).buffer;
    const credential = {
      id: "cred-1",
      rawId: buffer,
      type: "public-key",
      response: {
        clientDataJSON: buffer,
        authenticatorData: buffer,
        signature: buffer,
        userHandle: null,
      },
    } as unknown as PublicKeyCredential;
    expect(serializeCredential(credential)).toMatchObject({
      id: "cred-1",
      rawId: b64(new Uint8Array([11, 12])),
      response: {
        clientDataJSON: b64(new Uint8Array([11, 12])),
        authenticatorData: b64(new Uint8Array([11, 12])),
        signature: b64(new Uint8Array([11, 12])),
      },
    });
  });
});
