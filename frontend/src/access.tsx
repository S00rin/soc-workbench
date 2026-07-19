import { createContext, ReactNode, useContext } from "react";

export type FeatureState = {
  active: boolean;
  enabled: boolean;
  status: string;
  starts_at?: string | null;
  expires_at?: string | null;
  allowed_roles?: string[];
  config?: Record<string, unknown>;
};

export type AccessState = {
  user: { id: number; username: string; display_name: string; tenant_id: string; role: string };
  modules: string[];
  features: Record<string, FeatureState>;
  module_catalog: { key: string; label: string; description: string }[];
};

const AccessContext = createContext<AccessState | null>(null);

export function AccessProvider({ value, children }: { value: AccessState; children: ReactNode }) {
  return <AccessContext.Provider value={value}>{children}</AccessContext.Provider>;
}

export function useAccess(): AccessState {
  const value = useContext(AccessContext);
  if (!value) throw new Error("Access context is not available");
  return value;
}

export function hasModule(access: AccessState, module: string): boolean {
  return access.user.role === "admin" || access.modules.includes(module);
}

export function hasFeature(access: AccessState, feature: string): boolean {
  return access.features[feature]?.active !== false;
}
