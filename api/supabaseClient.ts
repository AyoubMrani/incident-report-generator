import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

console.log('Supabase URL:', supabaseUrl ? 'Set' : 'NOT SET');
console.log('Supabase Key:', serviceRoleKey ? 'Set' : 'NOT SET');

if (!supabaseUrl || !serviceRoleKey) {
  console.error('Missing Supabase server environment variables!', { supabaseUrl, serviceRoleKey });
  throw new Error(`Missing Supabase credentials: URL=${!!supabaseUrl}, Key=${!!serviceRoleKey}`);
}

export const supabaseServer = createClient(supabaseUrl, serviceRoleKey);
