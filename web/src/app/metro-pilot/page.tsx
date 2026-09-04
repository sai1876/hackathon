import Link from 'next/link';
import MetroOperations from '@/components/metro/MetroOperations';
import '@/components/metro/metro.css';
export default function MetroPilot(){return <main className="metro-page"><nav><Link href="/command">Command Center</Link><Link href="/metro-command">Metro Command</Link></nav><h1>Metro Pilot</h1><MetroOperations pilot/></main>;}
