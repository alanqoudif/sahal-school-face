import { Alert, Button, Card, Input, Label, TextField } from "@heroui/react";
import { FormEvent, useState } from "react";
import { login } from "../api";

export function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setPending(true);
    const form = new FormData(event.currentTarget);
    try {
      await login(String(form.get("password") || ""));
      onLoggedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "تعذر تسجيل الدخول");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
      <div className="mb-6 flex items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-2xl bg-accent text-lg font-extrabold text-accent-foreground">
          س
        </span>
        <span>
          <span className="block text-xl font-extrabold">سهل</span>
          <span className="block text-sm text-muted">دخول الإدارة</span>
        </span>
      </div>
      <Card>
        <Card.Header>
          <Card.Title>تسجيل الدخول</Card.Title>
          <Card.Description>أدخل كلمة مرور الجهاز عشان تفتح الطلاب والحضور والكاميرا.</Card.Description>
        </Card.Header>
        <form onSubmit={onSubmit}>
          <Card.Content className="grid gap-4">
            {error ? (
              <Alert status="danger">
                <Alert.Indicator />
                <Alert.Content>
                  <Alert.Title>{error}</Alert.Title>
                </Alert.Content>
              </Alert>
            ) : null}
            <TextField isRequired name="password" className="w-full">
              <Label>كلمة المرور</Label>
              <Input fullWidth type="password" autoFocus autoComplete="current-password" />
            </TextField>
          </Card.Content>
          <Card.Footer>
            <Button isPending={pending} type="submit" className="w-full">
              دخول
            </Button>
          </Card.Footer>
        </form>
      </Card>
    </div>
  );
}
