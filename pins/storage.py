"""
Optional Django Storage backend backed by Supabase Storage.

Only used when USE_SUPABASE_STORAGE=true is set in `.env` (see
config/settings.py). When disabled, Django's normal FileSystemStorage
handles pin images on local disk, which is all you need for a single-server
deployment or local development.

Requires the `supabase` package (already in requirements.txt) and a bucket
created in your Supabase project (Storage → New bucket). Make the bucket
public if you want pin images to be viewable via a plain URL — otherwise
you'll need to generate signed URLs instead of using `.url()` as-is.
"""

import mimetypes
import posixpath
import uuid
from io import BytesIO

from django.conf import settings
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class SupabaseStorage(Storage):
    def __init__(self):
        self.bucket_name = settings.SUPABASE_STORAGE_BUCKET
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from supabase import create_client

            self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        return self._client

    def _bucket(self):
        return self.client.storage.from_(self.bucket_name)

    def _open(self, name, mode='rb'):
        data = self._bucket().download(name)
        return BytesIO(data)

    def get_available_name(self, name, max_length=None):
        """
        Make the name unique WITHOUT asking Supabase whether it's taken.

        The default implementation calls exists() -> bucket.list() over the
        network (and Django calls it twice per save: once in Storage.save() and
        again inside the old _save()). On top of being slow, list() only returns
        the first 100 files of a folder by default, so on a busy folder a name
        collision went undetected and 'upsert' silently overwrote an older pin's
        image. A random suffix makes collisions practically impossible and costs
        nothing.
        """
        directory, filename = posixpath.split(name)
        stem, ext = posixpath.splitext(filename)
        suffix = f"_{uuid.uuid4().hex[:8]}"
        if max_length:  # ImageField's column is varchar(100) — keep the full path inside it
            room = max_length - len(directory) - (1 if directory else 0) - len(suffix) - len(ext)
            stem = stem[: max(room, 1)]
        unique = f"{stem}{suffix}{ext}"
        return posixpath.join(directory, unique) if directory else unique

    def _save(self, name, content):
        # `name` is already unique (see get_available_name) — one upload call, nothing else.
        content.seek(0)
        file_bytes = content.read()
        content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        self._bucket().upload(
            path=name,
            file=file_bytes,
            file_options={'content-type': content_type, 'upsert': 'false'},
        )
        return name

    def exists(self, name):
        folder = '/'.join(name.split('/')[:-1])
        filename = name.split('/')[-1]
        try:
            listing = self._bucket().list(folder)
        except Exception:
            return False
        return any(f.get('name') == filename for f in listing)

    def url(self, name):
        return self._bucket().get_public_url(name)

    def delete(self, name):
        self._bucket().remove([name])

    def size(self, name):
        # Supabase's list() response includes metadata with byte size; fall
        # back to 0 if it can't be resolved, since Django only uses this for
        # display purposes in most places.
        folder = '/'.join(name.split('/')[:-1])
        filename = name.split('/')[-1]
        try:
            listing = self._bucket().list(folder)
            for f in listing:
                if f.get('name') == filename:
                    return f.get('metadata', {}).get('size', 0)
        except Exception:
            pass
        return 0
