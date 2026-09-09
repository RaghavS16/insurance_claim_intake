import Link from "next/link";
import Head from "next/head";

export default function NotFound() {
  return (
    <>
      <Head>
        <title>Page Not Found | InsureClaimAI</title>
        <meta name="description" content="The page you are looking for could not be found." />
      </Head>
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#f8fafc",
          fontFamily: "system-ui, sans-serif",
          padding: "2rem",
          textAlign: "center",
        }}
      >
        <div
          style={{
            background: "white",
            borderRadius: "16px",
            padding: "3rem 4rem",
            boxShadow: "0 4px 24px rgba(0,0,0,0.06)",
            maxWidth: "480px",
            width: "100%",
          }}
        >
          <div
            style={{
              fontSize: "5rem",
              fontWeight: 800,
              color: "#0891B2",
              lineHeight: 1,
              marginBottom: "0.5rem",
            }}
          >
            404
          </div>
          <h1
            style={{
              fontSize: "1.5rem",
              fontWeight: 700,
              color: "#191c1e",
              marginBottom: "0.75rem",
            }}
          >
            Page not found
          </h1>
          <p style={{ color: "#505f76", fontSize: "0.95rem", marginBottom: "2rem" }}>
            The page you are looking for doesn&apos;t exist or has been moved.
          </p>
          <Link
            href="/"
            style={{
              display: "inline-block",
              padding: "0.75rem 2rem",
              background: "#0891B2",
              color: "white",
              borderRadius: "8px",
              textDecoration: "none",
              fontWeight: 600,
              fontSize: "0.9rem",
            }}
          >
            Return to Dashboard
          </Link>
        </div>
      </div>
    </>
  );
}
