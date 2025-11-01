import fetch from "node-fetch";

export default async function handler(req, res) {
  const { method, query } = req;
  const DEPLOY_KEY = process.env.DEPLOY_KEY;
  const TELEGRAM_TOKEN = process.env.TELEGRAM_TOKEN;
  const CHAT_ID = process.env.CHAT_ID;

  if (method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  if (query.secret !== DEPLOY_KEY) {
    return res.status(403).json({ error: "Forbidden" });
  }

  try {
    const message = `🚀 Redeploy triggered successfully on Vercel!\n\nTime: ${new Date().toLocaleString()}`;
    await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: CHAT_ID, text: message }),
    });

    const piResponse = await fetch("http://192.168.68.200:9090/redeploy", {
      method: "POST",
      headers: { "x-deploy-key": DEPLOY_KEY },
    });

    const result = await piResponse.text();

    return res.status(200).json({
      success: true,
      message: "Redeploy triggered successfully",
      piResponse: result,
    });
  } catch (error) {
    console.error("Redeploy error:", error);
    return res.status(500).json({ error: "Internal Server Error" });
  }
}
