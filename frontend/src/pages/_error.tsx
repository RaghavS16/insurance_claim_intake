import type { NextPageContext } from "next";
import Link from "next/link";
import Head from "next/head";

interface ErrorProps {
  statusCode?: number;
}

export default function ErrorPage({ statusCode }: ErrorProps) {
  const is500 = statusCode && statusCode >= 500;
  return (
    <>
      <Head>
        <title>{statusCode ? `${statusCode} Error` : "Error"} | InsureClaimAI</title>
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
              color: is500 ? "#ba1a1a" : "#0891B2",
              lineHeight: 1,
              marginBottom: "0.5rem",
            }}
          >
            {statusCode || "Error"}
          </div>
          <h1
            style={{
              fontSize: "1.5rem",
              fontWeight: 700,
              color: "#191c1e",
              marginBottom: "0.75rem",
            }}
          >
            {is500 ? "Server error" : "Something went wrong"}
          </h1>
          <p style={{ color: "#505f76", fontSize: "0.95rem", marginBottom: "2rem" }}>
            {is500
              ? "We're experiencing a technical issue. Please try again in a moment."
              : "An unexpected error occurred. Please try again."}
          </p>
          <Link
            href="/"
            style={{
              display: "inline-block",
              padding: "0.75rem 2rem",
              background: is500 ? "#ba1a1a" : "#0891B2",
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

ErrorPage.getInitialProps = ({ res, err }: NextPageContext): ErrorProps => {
  const statusCode = res ? res.statusCode : err ? (err as any).statusCode : 404;
  return { statusCode };
};
