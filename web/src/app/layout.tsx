import type { Metadata } from "next";
import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";
import "./command.css";
export const metadata: Metadata = { title: "AegisGrid | Hyderabad Urban Operations", description: "Real road routing, runtime incidents, and clearly labeled synthetic urban operations exercises" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
