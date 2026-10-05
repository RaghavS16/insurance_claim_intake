import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { 
  Badge, 
  Card, 
  CodeBlock, 
  DataBadge, 
  Empty, 
  MarkdownRenderer, 
  Metric, 
  ThemeToggle 
} from "./ui";

describe("Figma workspace UI primitives & Anti-Slop components", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.classList.remove("dark");
  });

  it("renders card and metric", () => {
    render(
      <>
        <Metric label="Filed claims" value="12" note="Current" />
        <Card>
          <Badge tone="success">Active</Badge>
        </Card>
      </>
    );
    expect(screen.getByText("Filed claims")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders DataBadge with mapped tones based on status", () => {
    const { rerender } = render(<DataBadge status="approved" />);
    expect(screen.getByText("approved")).toHaveClass("badge", "success");

    rerender(<DataBadge status="under_review" />);
    expect(screen.getByText("under review")).toHaveClass("badge", "warning");

    rerender(<DataBadge status="rejected" />);
    expect(screen.getByText("rejected")).toHaveClass("badge", "danger");
  });

  it("renders Empty state with text and optional action", () => {
    render(
      <Empty 
        text="No claims available" 
        action={<button>Create claim</button>} 
      />
    );
    expect(screen.getByText("No claims available")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create claim" })).toBeInTheDocument();
  });

  it("cycles theme between light, dark, and system", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: "Toggle color theme" });

    // Initial is system
    expect(button).toHaveAttribute("title", "Theme: SYSTEM (Click to cycle)");

    // Click 1: System -> Light
    fireEvent.click(button);
    expect(localStorage.getItem("flowa-theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    // Click 2: Light -> Dark
    fireEvent.click(button);
    expect(localStorage.getItem("flowa-theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    // Click 3: Dark -> System
    fireEvent.click(button);
    expect(localStorage.getItem("flowa-theme")).toBe("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("renders MarkdownRenderer with paragraphs, bold, lists, and fenced code blocks", () => {
    const content = `
### Claim Summary
Here is your **verified claim** details:
- Vehicle: Honda Civic 2024
- Damage: Front bumper
- Estimated cost: $1,200

\`\`\`json
{
  "claim_type": "auto",
  "priority": "normal"
}
\`\`\`
    `.trim();

    render(<MarkdownRenderer content={content} />);

    expect(screen.getByRole("heading", { level: 3, name: "Claim Summary" })).toBeInTheDocument();
    expect(screen.getByText("verified claim")).toBeInTheDocument();
    expect(screen.getByText("Vehicle: Honda Civic 2024")).toBeInTheDocument();
    expect(screen.getByText("JSON")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy code block" })).toBeInTheDocument();
  });

  it("copies code to clipboard in CodeBlock", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: { writeText }
    });

    render(<CodeBlock code="const status = 'verified';" language="typescript" />);
    const copyButton = screen.getByRole("button", { name: "Copy code block" });
    await React.act(async () => {
      fireEvent.click(copyButton);
    });

    expect(writeText).toHaveBeenCalledWith("const status = 'verified';");
  });
});
