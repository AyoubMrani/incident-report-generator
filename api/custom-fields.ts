import { VercelRequest, VercelResponse } from '@vercel/node';
import { createClient } from '@supabase/supabase-js';
import crypto from 'crypto';

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

// Generate a UUID v4
function generateUUID(): string {
  return crypto.randomUUID();
}

export default async (req: VercelRequest, res: VercelResponse) => {
  if (!supabaseServer) {
    return res.status(500).json({ error: 'Supabase not configured' });
  }

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
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

      console.log('Returning fields:', customFields);
      console.log('Returning categories:', customCategories);
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

      // Insert/update categories - generate UUIDs if missing
      for (const category of customCategories) {
        const uuid = category.id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(category.id) ? category.id : generateUUID();
        console.log('Upserting category with UUID:', uuid, 'label:', category.label);
        const { data, error: catError } = await supabaseServer
          .from('custom_categories')
          .upsert({ id: uuid, label: category.label }, { onConflict: 'label' })
          .select();
        
        if (catError) {
          const errMsg = `Error upserting category: ${catError.message}`;
          console.error(errMsg);
          errors.push(errMsg);
        } else {
          console.log('Category upserted successfully:', data);
        }
      }

      // Insert/update fields - generate UUIDs if missing
      for (const field of customFields) {
        if (field.isPermanent !== false) {
          const uuid = field.id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(field.id) ? field.id : generateUUID();
          console.log('Upserting field with UUID:', uuid, 'name:', field.name);
          const { data, error: fieldError } = await supabaseServer
            .from('custom_fields')
            .upsert({
              id: uuid,
              name: field.name,
              label: field.label,
              is_permanent: field.isPermanent !== false,
            }, { onConflict: 'name' })
            .select();
          
          if (fieldError) {
            const errMsg = `Error upserting field: ${fieldError.message}`;
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

    // DELETE - Delete a custom field or category
    if (req.method === 'DELETE') {
      const { fieldId, fieldName, categoryLabel, type } = req.body;

      console.log('Deleting:', { type, fieldId, fieldName, categoryLabel });

      if (type === 'field' && (fieldId || fieldName)) {
        let error;
        if (fieldName) {
          // Delete by name
          const { error: err } = await supabaseServer
            .from('custom_fields')
            .delete()
            .eq('name', fieldName);
          error = err;
        } else {
          // Delete by id
          const { error: err } = await supabaseServer
            .from('custom_fields')
            .delete()
            .eq('id', fieldId);
          error = err;
        }

        if (error) {
          console.error('Error deleting field:', error);
          return res.status(400).json({ success: false, error: `Failed to delete field: ${error.message}` });
        }

        console.log('Field deleted successfully');
        return res.status(200).json({ success: true, message: 'Field deleted' });
      }

      if (type === 'category' && (categoryLabel || fieldId)) {
        let error;
        if (categoryLabel) {
          // Delete by label
          const { error: err } = await supabaseServer
            .from('custom_categories')
            .delete()
            .eq('label', categoryLabel);
          error = err;
        } else {
          // Delete by id
          const { error: err } = await supabaseServer
            .from('custom_categories')
            .delete()
            .eq('id', fieldId);
          error = err;
        }

        if (error) {
          console.error('Error deleting category:', error);
          return res.status(400).json({ success: false, error: `Failed to delete category: ${error.message}` });
        }

        console.log('Category deleted successfully');
        return res.status(200).json({ success: true, message: 'Category deleted' });
      }

      return res.status(400).json({ error: 'Missing required delete parameters' });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (error) {
    console.error('Error in custom-fields endpoint:', error);
    return res.status(500).json({ error: 'Failed to process custom fields', details: String(error) });
  }
};
