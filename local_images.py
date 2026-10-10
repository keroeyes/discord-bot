"""Local-only ComfyUI client. No hosted models, arbitrary workflow or retries."""
import asyncio
import secrets
import aiohttp

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def workflow(prompt, checkpoint, seed):
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 2000:
        raise ValueError('Invalid prompt')
    if not checkpoint or '/' in checkpoint or '\\' in checkpoint:
        raise ValueError('Invalid checkpoint')
    return {
        '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': checkpoint}},
        '2': {'class_type': 'CLIPTextEncode', 'inputs': {'text': prompt, 'clip': ['1', 1]}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': 'blurry, low quality, watermark', 'clip': ['1', 1]}},
        '4': {'class_type': 'EmptyLatentImage', 'inputs': {'width': 1024, 'height': 1024, 'batch_size': 1}},
        '5': {'class_type': 'KSampler', 'inputs': {'model': ['1', 0], 'positive': ['2', 0], 'negative': ['3', 0], 'latent_image': ['4', 0], 'seed': seed, 'steps': 25, 'cfg': 7.0, 'sampler_name': 'euler', 'scheduler': 'normal', 'denoise': 1.0}},
        '6': {'class_type': 'VAEDecode', 'inputs': {'samples': ['5', 0], 'vae': ['1', 2]}},
        '7': {'class_type': 'SaveImage', 'inputs': {'images': ['6', 0], 'filename_prefix': 'keroro'}},
    }


class LocalImages:
    def __init__(self, checkpoint, port=8188, timeout=180):
        if not 1 <= port <= 65535:
            raise ValueError('Invalid port')
        self.base = f'http://127.0.0.1:{port}'
        self.checkpoint = checkpoint
        self.timeout = timeout

    async def generate(self, prompt, *, seed=None):
        # Fixed seeds are opt-in for synthetic A/B checks; normal requests stay random.
        if seed is not None and (type(seed) is not int or not 0 <= seed < 2 ** 63):
            raise ValueError('Invalid seed')
        graph = workflow(prompt, self.checkpoint, secrets.randbits(63) if seed is None else seed)
        async with asyncio.timeout(self.timeout):
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), trust_env=False) as session:
                async with session.post(self.base + '/prompt', json={'prompt': graph}, allow_redirects=False) as response:
                    response.raise_for_status()
                    result = await response.json()
                if result.get('error') or result.get('node_errors'):
                    raise RuntimeError('Workflow rejected')
                prompt_id = result.get('prompt_id')
                if not isinstance(prompt_id, str) or not prompt_id or any(c not in '0123456789abcdef-' for c in prompt_id.lower()):
                    raise ValueError('Invalid job identifier')
                while True:
                    async with session.get(self.base + '/history/' + prompt_id, allow_redirects=False) as response:
                        response.raise_for_status()
                        history = await response.json()
                    job = history.get(prompt_id)
                    if job:
                        if job.get('status', {}).get('status_str') == 'error':
                            raise RuntimeError('Generation failed')
                        images = job.get('outputs', {}).get('7', {}).get('images', [])
                        if images:
                            item = images[0]
                            if item.get('type') != 'output':
                                raise ValueError('Invalid output')
                            params = {key: item.get(key, '') for key in ('filename', 'subfolder', 'type')}
                            if any(not isinstance(v, str) for v in params.values()):
                                raise ValueError('Invalid output')
                            async with session.get(self.base + '/view', params=params, allow_redirects=False) as response:
                                response.raise_for_status()
                                data = bytearray()
                                async for chunk in response.content.iter_chunked(65536):
                                    data.extend(chunk)
                                    if len(data) > MAX_IMAGE_BYTES:
                                        raise ValueError('Image exceeds upload budget')
                            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                                raise ValueError('Invalid image')
                            return bytes(data)
                    await asyncio.sleep(1)
