import { VercelRequest, VercelResponse } from '@vercel/node';
import { createClient } from '@supabase/supabase-js';

// Initialize Supabase client
const supabaseUrl = process.env.SUPABASE_URL;
const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const supabaseServer = supabaseUrl && serviceRoleKey 
  ? createClient(supabaseUrl, serviceRoleKey)
  : null;

interface CustomField {
  id: string;
  name: string;
  label: string;
  isPermanent?: boolean;
}

interface CustomCategory {
  id: string;
  label: string;
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
    // GET - Fetch custom fields and categories from database
    if (req.method === 'GET') {
      console.log('Fetching custom fields and categories from database');

      // Fetch from database tables
      const { data: categories, error: catError } = await supabaseServer
        .from('custom_categories')
        .select('*')
        .order('created_at', { ascending: true });

      const { data: fields, error: fieldsError } = await supabaseServer
        .from('custom_fields')
        .select('*')
        .eq('is_permanent', true)
        .order('created_at', { ascending: true });

      if (catError) {
        console.log('Categories table may not exist yet:', catError);
      }
      if (fieldsError) {
        console.log('Fields table may not exist yet:', fieldsError);
      }

      const customFields: CustomField[] = (fields || []).map(f => ({
        id: f.id,
        name: f.name,
        label: f.label,
        isPermanent: f.is_permanent,
      }));

      const customCategories: CustomCategory[] = (categories || []).map(c => ({
        id: c.id,
        label: c.label,
      }));

      return res.status(200).json({ customFields, customCategories });
    }

    // POST - Save custom fields and categories to database
    if (req.method === 'POST') {
      const { customFields, customCategories } = req.body;

      if (!customFields || !customCategories) {
        return res.status(400).json({ error: 'customFields and customCategories are required' });
      }

      console.log('Saving custom fields and categories to database');
      console.log('Categories to save:', customCategories);
      console.log('Fields to save:', customFields);

      const errors: string[] = [];

      // Insert/update categories
      for (const category of customCategories) {
        console.log('Upserting category:', category);
        const { data, error: catError } = await supabaseServer
          .from('custom_categories')
          .upsert({ id: category.id, label: category.label }, { onConflict: 'id' })
          .select();
        
        if (catError) {
          const errMsg = `Error upserting category ${category.id}: ${catError.message}`;
          console.error(errMsg);
          errors.push(errMsg);
        } else {
          console.log('Category upserted successfully:', data);
        }
      }

      // Insert/update fields (only permanent ones)
      for (const field of customFields) {
        if (field.isPermanent !== false) {
          console.log('Upserting field:', field);
          const { data, error: fieldError } = await supabaseServer
            .from('custom_fields')
            .upsert({
              id: field.id,
              name: field.name,
              label: field.label,
              is_permanent: field.isPermanent !== false,
            }, { onConflict: 'id' })
            .select();
          
          if (fieldError) {
            const errMsg = `Error upserting field ${field.id}: ${fieldError.message}`;
            console.error(errMsg);
            errors.push(errMsg);
          } else {
            console.log('Field upserted successfully:', data);
          }
        }
      }

      if (errors.length > 0) {
        console.error('There were errors saving:', errors);
        return res.status(400).json({ success: false, errors, message: 'Some fields failed to save' });
      }

      console.log('Custom fields saved to database successfully');
      return res.status(200).json({ success: true, message: 'Custom fields saved to database' });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (error) {
    console.error('Error in custom-fields endpoint:', error);
    return res.status(500).json({ error: 'Failed to process custom fields', details: String(error) });
  }
};
