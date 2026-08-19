import { Html, Head, Main, NextScript } from "next/document";

export default function Document() {
  return (
    <Html lang="en" className="dark">
      <Head>
        <title>Insurance Claim Intake Voice Agent</title>
        <meta name="description" content="AI-Powered Conversational Insurance Claim Intake & Extraction" />
      </Head>
      <body className="bg-slate-950 text-slate-100 min-h-screen antialiased">
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
