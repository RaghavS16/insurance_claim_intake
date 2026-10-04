import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

let pathname = "/register";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api", () => ({
  api: vi.fn(),
}));

import { RouterView } from "./workspace";

describe("authentication routing", () => {
  beforeEach(() => {
    pathname = "/register";
    localStorage.clear();
  });

  it("renders registration directly without requiring an access token", () => {
    render(<RouterView />);
    expect(screen.getByRole("heading", { name: "Create your claimant account" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("renders login directly without entering the workspace shell", () => {
    pathname = "/login";
    render(<RouterView />);
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("renders recovery directly", () => {
    pathname = "/recovery";
    render(<RouterView />);
    expect(screen.getByRole("heading", { name: "Account recovery" })).toBeInTheDocument();
  });
});
