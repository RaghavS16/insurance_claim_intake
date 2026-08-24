import type { AppProps } from "next/app";
import Head from "next/head";
import "@/styles/globals.css";

export default function MyApp({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        <title>InsureClaimAI</title>
        <meta name="description" content="A Voice driven Agentic AI System for Insurance Claim intake and adjudication" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      </Head>
      <Component {...pageProps} />
    </>
  );
}
