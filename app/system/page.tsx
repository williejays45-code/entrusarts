export const dynamic = "force-static";

export default function Page() {
  return (
    <main style={{ margin: 0, padding: 0, height: "100vh" }}>
      <iframe
        src="/legacy/system.html"
        style={{ width: "100%", height: "100%", border: "0" }}
        title="EnTrus System"
      />
    </main>
  );
}
