import { VercelRequest, VercelResponse } from '@vercel/node';

export default async (req: VercelRequest, res: VercelResponse) => {
  res.json({
    message: 'API is working!',
    supabaseUrl: process.env.SUPABASE_URL ? '✅ Set' : '❌ Missing',
    supabaseKey: process.env.SUPABASE_SERVICE_ROLE_KEY ? '✅ Set' : '❌ Missing',
    nodeEnv: process.env.NODE_ENV,
    timestamp: new Date().toISOString(),
  });
};
