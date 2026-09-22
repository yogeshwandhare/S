import { type FormEvent, useState } from "react";
import { Plus, Shield, UserX } from "lucide-react";

import { PageHeader } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useModels } from "@/hooks/useCameras";
import { useAuditLogs, useCreateUser, useToggleUserActive, useUsers } from "@/hooks/useSettings";
import { ApiError } from "@/lib/api";

const TABS = ["Users", "Models", "Audit Log"] as const;
type Tab = (typeof TABS)[number];

function UsersPanel() {
  const { data: users } = useUsers();
  const createUser = useCreateUser();
  const toggleActive = useToggleUserActive();
  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createUser.mutate(
      { email, full_name: fullName, password, role },
      {
        onSuccess: () => {
          setShowForm(false);
          setEmail("");
          setFullName("");
          setPassword("");
        },
        onError: (err) =>
          setError(err instanceof ApiError ? err.message : "Failed to create user"),
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Users</CardTitle>
        {!showForm && (
          <Button size="sm" onClick={() => setShowForm(true)}>
            <Plus className="h-3.5 w-3.5" />
            Add user
          </Button>
        )}
      </CardHeader>

      {showForm && (
        <form onSubmit={handleSubmit} className="space-y-3 border-b border-border p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <input
              required
              type="email"
              placeholder="email@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
            />
            <input
              required
              placeholder="Full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
            />
            <input
              required
              type="password"
              placeholder="Password (10+ chars)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={10}
              className="rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none focus-visible:border-cyan"
            />
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="rounded-md border border-border-strong bg-surface-raised px-3 py-1.5 text-sm text-text outline-none"
            >
              <option value="viewer">Viewer</option>
              <option value="operator">Operator</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          {error && <p className="text-sm text-severity-critical">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={createUser.isPending}>
              Create
            </Button>
          </div>
        </form>
      )}

      <div className="divide-y divide-border">
        {users?.map((u) => (
          <div key={u.id} className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-sm text-text">{u.full_name}</p>
              <p className="text-xs text-text-faint">
                {u.email} · <span className="capitalize">{u.role}</span>
                {!u.is_active && <span className="text-severity-critical"> · disabled</span>}
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => toggleActive.mutate({ id: u.id, activate: !u.is_active })}
            >
              <UserX className="h-3.5 w-3.5" />
              {u.is_active ? "Disable" : "Enable"}
            </Button>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ModelsPanel() {
  const { data: models } = useModels();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Model registry</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 text-sm text-text-muted">
        <p className="mb-3">
          Models are enabled via{" "}
          <code className="rounded bg-surface-raised px-1">scripts/download_models.py</code>, not
          through this page — enabling an AGPL-licensed model is a deliberate, explicit action.
        </p>
      </CardContent>
      <div className="divide-y divide-border">
        {models?.map((m) => (
          <div key={m.id} className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-sm text-text">{m.name}</p>
              <p className="text-xs text-text-faint">
                {m.task.replace("_", " ")} · {m.license}
              </p>
            </div>
            <span
              className={`rounded-full border px-2 py-0.5 text-xs ${
                m.enabled
                  ? "border-teal/30 bg-teal/10 text-teal"
                  : "border-text-faint/30 bg-text-faint/10 text-text-muted"
              }`}
            >
              {m.enabled ? "Enabled" : m.is_available ? "Available" : "Not configured"}
            </span>
          </div>
        ))}
        {models?.length === 0 && (
          <p className="px-4 py-6 text-center text-sm text-text-muted">
            No models registered yet. Run scripts/download_models.py.
          </p>
        )}
      </div>
    </Card>
  );
}

function AuditLogPanel() {
  const { data: logs } = useAuditLogs();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Audit log</CardTitle>
      </CardHeader>
      <div className="divide-y divide-border">
        {logs?.map((log) => (
          <div key={log.id} className="flex items-center justify-between px-4 py-2.5">
            <div className="flex items-center gap-2">
              <Shield className="h-3.5 w-3.5 text-text-faint" />
              <div>
                <p className="text-sm text-text">{log.action.replace(/_/g, " ")}</p>
                {log.detail && <p className="text-xs text-text-faint">{log.detail}</p>}
              </div>
            </div>
            <p className="text-xs text-text-faint">{new Date(log.created_at).toLocaleString()}</p>
          </div>
        ))}
        {logs?.length === 0 && (
          <p className="px-4 py-6 text-center text-sm text-text-muted">No audit entries yet.</p>
        )}
      </div>
    </Card>
  );
}

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>("Users");

  return (
    <div className="flex flex-1 flex-col">
      <PageHeader title="Settings" description="Users, model status, and audit trail." />

      <div className="flex gap-2 border-b border-border bg-surface px-6 py-3">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-full border px-3 py-1 text-xs ${
              tab === t
                ? "border-cyan/40 bg-cyan/10 text-cyan"
                : "border-border-strong text-text-muted hover:text-text"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-4 overflow-auto p-6">
        {tab === "Users" && <UsersPanel />}
        {tab === "Models" && <ModelsPanel />}
        {tab === "Audit Log" && <AuditLogPanel />}
      </div>
    </div>
  );
}
