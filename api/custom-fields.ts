import { VercelRequest, VercelResponse } from '@vercel/node';
import { createClient } from '@supabase/supabase-js';

const BUCKET_NAME = 'reports';

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const supabaseServer = supabaseUrl && serviceRoleKey 
  ? createClient(supabaseUrl, serviceRoleKey)
  : null;

interface CustomField {
  id: string;
  name: string;
  isPermanent: boolean;
}

interface CustomCategory {
  id: string;
  name: string;
}

export default async (req: VercelRequest, res: VercelResponse) => {
  if (!supabaseServer) {
    return res.status(500).json({ error: 'Supabase not configured' });
  }

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  try {
    // GET - Fetch custom fields and categories
    if (req.method === 'GET') {
      console.log('Fetching custom fields and categories');

      // Try to fetch from files storage (fallback approach)
      // For now, return empty arrays if table doesn't exist
      const customFields: CustomField[] = [];
      const customCategories: CustomCategory[] = [];

      // Try to read from a JSON file in storage
      try {
        const { data, error } = await supabaseServer.storage
          .from(BUCKET_NAME)
          .download('config/custom-fields.json');

        if (!error) {
          const content = await data.text();
          const parsed = JSON.parse(content);
          customFields.push(...(parsed.fields || []));
          customCategories.push(...(parsed.categories || []));
        }
      } catch (err) {
        console.log('No custom fields config found yet');
      }

      return res.status(200).json({ customFields, customCategories });
    }

    // POST - Save custom fields and categories
    if (req.method === 'POST') {
      const { customFields, customCategories } = req.body;

      if (!customFields || !customCategories) {
        return res.status(400).json({ error: 'customFields and customCategories are required' });
      }

      console.log('Saving custom fields and categories');

      const configData = {
        fields: customFields,
        categories: customCategories,
        updatedAt: new Date().toISOString(),
      };

      try {
        // Try to delete existing file first
        await supabaseServer.storage
          .from(BUCKET_NAME)
          .remove(['config/custom-fields.json']);
      } catch (err) {
        console.log('No existing config to delete');
      }

      // Upload new config
      const { error } = await supabaseServer.storage
        .from(BUCKET_NAME)
        .upload('config/custom-fields.json', JSON.stringify(configData, null, 2), {
          contentType: 'application/json',
        });

      if (error) {
        console.error('Error saving custom fields:', error);
        throw error;
      }

      console.log('Custom fields saved successfully');
      return res.status(200).json({ success: true, message: 'Custom fields saved' });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (error) {
    console.error('Error in custom-fields endpoint:', error);
    return res.status(500).json({ error: 'Failed to process custom fields', details: String(error) });
  }
};
