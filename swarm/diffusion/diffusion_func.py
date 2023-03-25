import torch
from diffusers import (
    StableDiffusionPipeline,
    DPMSolverMultistepScheduler,
    StableDiffusionLatentUpscalePipeline,
)
from .output_processor import OutputProcessor


def diffusion_callback(device_id, model_name, **kwargs):
    scheduler_type = kwargs.pop("scheduler_type", DPMSolverMultistepScheduler)
    pipeline_type = kwargs.pop("pipeline_type", StableDiffusionPipeline)
    upscale = kwargs.pop("upscale", False)
    if upscale:  # if upscaling stay in latent space
        kwargs["output_type"] = "latent"

    pipeline = pipeline_type.from_pretrained(
        model_name,
        revision=kwargs.pop("revision"),
        torch_dtype=torch.float16,
    )
    pipeline = pipeline.to(f"cuda:{device_id}")  # type: ignore

    pipeline.scheduler = scheduler_type.from_config(  # type: ignore
        pipeline.scheduler.config  # type: ignore
    )

    output_processor = OutputProcessor(
        kwargs.pop("outputs", ["primary"]),
        kwargs.pop("content_type", "image/jpeg"),
    )

    if output_processor.need_intermediates():
        print("Capturing latents")

        def latents_callback(i, t, latents):
            output_processor.add_latents(pipeline, latents)  # type: ignore

        kwargs["callback"] = latents_callback
        kwargs["callback_steps"] = 5

    # if we're upscaling we need to preserve memory as it can OOM with even 12GB
    if upscale or kwargs["num_images_per_prompt"] > 1:
        pipeline.enable_attention_slicing()
        pipeline.enable_vae_slicing()  # type: ignore
        pipeline.enable_vae_tiling()  # type: ignore
        pipeline.enable_sequential_cpu_offload()  # type: ignore

    p = pipeline(**kwargs)  # type: ignore

    # if any image is nsfw, flag the entire result
    if (
        hasattr(p, "nsfw_content_detected")
        and p.nsfw_content_detected is not None  # type: ignore
        and len(p.nsfw_content_detected) >= 1  # type: ignore
    ):
        for _ in filter(lambda nsfw: nsfw, p.nsfw_content_detected):  # type: ignore
            pipeline.config["nsfw"] = True

    images = p.images  # type: ignore
    if upscale:
        images = upscale_latents(
            images, device_id, kwargs["prompt"], kwargs["num_images_per_prompt"]
        )

    output_processor.add_outputs(images)
    return (output_processor.get_results(), pipeline.config)  # type: ignore


def upscale_latents(low_res_latents, device_id, prompt, num_images_per_prompt):
    print("Upscaling...")
    upscaler = StableDiffusionLatentUpscalePipeline.from_pretrained(
        "stabilityai/sd-x2-latent-upscaler",
        torch_dtype=torch.float16,
    )

    upscaler = upscaler.to(f"cuda:{device_id}")  # type: ignore
    upscaler.enable_attention_slicing()
    upscaler.enable_sequential_cpu_offload()  # type: ignore

    if num_images_per_prompt > 1:
        prompt = [prompt] * num_images_per_prompt

    image = upscaler(  # type: ignore
        prompt=prompt, image=low_res_latents, num_inference_steps=20, guidance_scale=0
    ).images[  # type: ignore
        0
    ]  # type: ignore

    return [image]
