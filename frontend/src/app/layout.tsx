import type { Metadata } from "next";
import "./globals.css";
export const metadata:Metadata={title:"Flowa Insurance Claims",description:"Production insurance claim intake and adjuster workspace"};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
