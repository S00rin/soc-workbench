import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AccessProvider, AccessState } from "./access";
import Layout from "./components/Layout";
import { Markdown } from "./lib";

const access: AccessState = {
  user: { id: 2, username: "viewer", display_name: "SOC Viewer", tenant_id: "default", role: "viewer" },
  modules: ["dashboard", "data"],
  features: {
    "module.dashboard": { enabled: true, active: true, status: "active" },
    "module.data": { enabled: true, active: true, status: "active" },
  },
  module_catalog: [],
};

describe("safe product shell", () => {
  it("sanitizes connector markdown before rendering", () => {
    const { container } = render(<Markdown text={'<img src=x onerror="alert(1)"> [unsafe](javascript:alert(1)) **safe**'} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).not.toHaveAttribute("href");
    expect(screen.getByText("safe")).toBeInTheDocument();
  });

  it("shows only modules allowed by effective backend access", () => {
    render(<MemoryRouter><AccessProvider value={access}><Layout onLogout={vi.fn()}><div>content</div></Layout></AccessProvider></MemoryRouter>);
    expect(screen.getByText("Data & IoCs")).toBeInTheDocument();
    expect(screen.queryByText("Integration Hub")).not.toBeInTheDocument();
    expect(screen.queryByText("Access & Features")).not.toBeInTheDocument();
    expect(screen.queryByText("Price Analyzer")).not.toBeInTheDocument(); // not in this viewer's granted modules
    expect(screen.getByText("Help Guides")).toBeInTheDocument(); // help has no module gate; always visible
    expect(screen.getByAltText("Soorin logo")).toBeInTheDocument();
  });
});
