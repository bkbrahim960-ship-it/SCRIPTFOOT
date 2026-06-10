// ============================================================
//  Example: ربط موقع React/Vue/Next.js بالسكريبت
//  ضع هذا الكود في أي component في مشروعك
// ============================================================

// --- ملف: api/matches.js (أو استخدمه مباشرة) ---

const API_BASE = "https://your-app.onrender.com"; // ← غير الرابط بعد النشر

export async function getMatches(status = null, league = null) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (league) params.append("league", league);

  const res = await fetch(`${API_BASE}/api/matches?${params}`);
  return res.json();
}

export async function getLiveMatches() {
  const res = await fetch(`${API_BASE}/api/matches/live`);
  return res.json();
}

export async function getMatchById(id) {
  const res = await fetch(`${API_BASE}/api/matches/${id}`);
  return res.json();
}

// --- ملف: components/MatchesList.jsx (React) ---

import { useState, useEffect } from "react";
import { getLiveMatches } from "../api/matches";

export default function MatchesList() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const data = await getLiveMatches();
        setMatches(data.data);
      } catch (err) {
        console.error("Failed to fetch matches:", err);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
    // تحديث كل 60 ثانية
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div>Loading matches...</div>;

  return (
    <div className="matches-container">
      <h2>المباريات المباشرة</h2>
      {matches.length === 0 && <p>لا توجد مباريات مباشرة حالياً</p>}
      {matches.map((match) => (
        <div key={match.id} className="match-card">
          <div className="match-title">{match.title}</div>
          {match.league && <div className="match-league">{match.league}</div>}
          {match.score && <div className="match-score">{match.score}</div>}
          <div className="match-channels">
            {match.channels?.map((ch, i) => <span key={i}>{ch}</span>)}
          </div>
          <div className="match-time">{match.match_time}</div>

          {/* روابط البث */}
          {match.streams?.length > 0 && (
            <div className="stream-links">
              <h4>روابط المشاهدة:</h4>
              {match.streams.map((stream, i) => (
                <a
                  key={i}
                  href={stream.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="stream-btn"
                >
                  {stream.quality ? `${stream.quality}` : "بث مباشر"}
                  {stream.channel && ` - ${stream.channel}`}
                </a>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
