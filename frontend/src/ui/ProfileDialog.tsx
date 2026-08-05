// Profile editor: display name and picture.
//
// Only these two fields. Username, email, password and roles belong to
// Keycloak — editing them here would create a second source of truth for the
// identity the token asserts.
//
// The picture is downscaled and re-encoded in the browser before upload. A
// phone photo is several MB; the server caps the payload at ~190 KB, so
// without client-side resizing most real uploads would simply be rejected.

import React, { useEffect, useRef, useState } from 'react';
import { Camera, Loader2, Trash2, X } from 'lucide-react';
import { getProfile, updateProfile } from '../api/chat';
import { useToast } from './Toast';
import { NTT_BLUE } from './Brand';

const AVATAR_PX = 256;      // stored size; displayed at 32-72px
const JPEG_QUALITY = 0.82;

interface Props {
  open: boolean;
  onClose: () => void;
  /** Current values, so the dialog opens populated before its fetch lands. */
  initialName: string;
  initialAvatar: string;
  onSaved: (profile: { display_name: string; avatar_url: string }) => void;
}

/**
 * Read a File, downscale to a square, and return a JPEG data URI.
 *
 * Cropped to a centred square rather than stretched: an avatar is rendered in
 * a circle, and a squashed face is worse than a cropped one.
 */
async function toAvatarDataUri(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = AVATAR_PX;

  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Canvas unavailable');
  ctx.drawImage(
    bitmap,
    (bitmap.width - side) / 2,
    (bitmap.height - side) / 2,
    side,
    side,
    0,
    0,
    AVATAR_PX,
    AVATAR_PX,
  );
  bitmap.close?.();
  // JPEG, not PNG: a photo as PNG is several times larger and would blow the
  // server's size cap for no visible gain at this resolution.
  return canvas.toDataURL('image/jpeg', JPEG_QUALITY);
}

export default function ProfileDialog({
  open,
  onClose,
  initialName,
  initialAvatar,
  onSaved,
}: Props) {
  const [name, setName] = useState(initialName);
  const [avatar, setAvatar] = useState(initialAvatar);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const toast = useToast();

  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setAvatar(initialAvatar);
    // Refresh from the server: another tab may have changed it.
    getProfile()
      .then((p) => {
        if (p.display_name) setName(p.display_name);
        setAvatar(p.avatar_url || '');
      })
      .catch(() => { /* the passed-in values are a fine fallback */ });
  }, [open, initialName, initialAvatar]);

  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [open, onClose]);

  if (!open) return null;

  const pickImage = async (file: File) => {
    setBusy(true);
    try {
      setAvatar(await toAvatarDataUri(file));
    } catch {
      toast.error('Could not read that image. Try a PNG or JPEG.');
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const saved = await updateProfile({
        display_name: name.trim(),
        avatar_url: avatar,
      });
      onSaved(saved);
      toast.success('Profile updated');
      onClose();
    } catch (err) {
      toast.error((err as Error).message || 'Could not save your profile.');
    } finally {
      setSaving(false);
    }
  };

  const initials =
    (name || 'U')
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0]?.toUpperCase() ?? '')
      .join('') || 'U';

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Profile"
    >
      <div
        className="w-full max-w-sm rounded-xl border border-app bg-app-elevated shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5 dark:border-slate-800">
          <h2 className="text-[15px] font-semibold text-app">
            Profile
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-5">
          <div className="flex items-center gap-4">
            <div className="relative">
              {avatar ? (
                <img
                  src={avatar}
                  alt=""
                  className="h-[72px] w-[72px] rounded-full object-cover ring-1 ring-slate-200 dark:ring-slate-700"
                />
              ) : (
                <div
                  className="flex h-[72px] w-[72px] items-center justify-center rounded-full text-xl font-semibold text-white"
                  style={{ background: NTT_BLUE }}
                >
                  {initials}
                </div>
              )}
              {busy && (
                <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/40">
                  <Loader2 className="w-5 h-5 animate-spin text-white" />
                </div>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void pickImage(f);
                  e.target.value = '';
                }}
              />
              <button
                onClick={() => fileRef.current?.click()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-[12px] font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                <Camera className="w-3.5 h-3.5" />
                {avatar ? 'Change picture' : 'Upload picture'}
              </button>
              {avatar && (
                <button
                  onClick={() => setAvatar('')}
                  className="inline-flex items-center gap-1.5 px-1 text-[12px] text-slate-500 transition hover:text-red-600 dark:text-slate-400"
                >
                  <Trash2 className="w-3.5 h-3.5" /> Remove
                </button>
              )}
            </div>
          </div>

          <label className="mt-6 block">
            <span className="mb-1.5 block text-[12px] font-medium text-slate-700 dark:text-slate-300">
              Display name
            </span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              placeholder="Your name"
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-900 outline-none transition focus:border-slate-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </label>

          <p className="mt-3 text-[11px] leading-relaxed text-slate-400">
            Your username, email and roles are managed in Keycloak and cannot be
            changed here.
          </p>
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3.5 dark:border-slate-800">
          <button
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-[13px] font-medium text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving || busy}
            className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-[13px] font-medium text-white transition hover:brightness-110 disabled:opacity-50"
            style={{ background: NTT_BLUE }}
          >
            {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
