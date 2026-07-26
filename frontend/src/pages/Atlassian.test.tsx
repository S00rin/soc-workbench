import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../lib";
import Atlassian from "./Atlassian";

describe("Atlassian integration workspace", () => {
  beforeEach(() => {
    localStorage.setItem("soc_token", "test-token");
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/atlassian/connections")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ detail: "not mocked" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("renders the empty state and opens the production connection form", async () => {
    render(
      <MemoryRouter>
        <ToastProvider><Atlassian /></ToastProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Atlassian Integrations" })).toBeInTheDocument();
    expect(screen.getByText(/No connection yet/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "+ Add connection" }));
    expect(screen.getByRole("heading", { name: "Add Atlassian connection" })).toBeInTheDocument();
    expect(screen.getByLabelText("Deployment")).toBeInTheDocument();
    expect(screen.getByLabelText("Authentication")).toBeInTheDocument();
    expect(screen.getByText("OAuth 2.0 (3LO)")).toBeInTheDocument();
    expect(screen.getByText("Bulk auto-post")).toBeInTheDocument();
  });
});
