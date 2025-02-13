import numpy as np
import onnxruntime
import torch
from librosa import istft
from loguru import logger

from pipecat.frames.frames import FilterControlFrame
from pipecat.filters.base_audio_filter import BaseAudioFilter

class GTCRNNoiseReductionFilter(BaseAudioFilter):
    def __init__(self, model_path: str):
        """Initialize the GTCRN noise reduction filter.
        
        Args:
            model_path: Path to the GTCRN ONNX model file
        """
        self._model_path = model_path
        self._session = None
        self._sample_rate = None
        
        # STFT parameters
        self._n_fft = 512
        self._hop_length = 256
        self._win_length = 512
        self._window = torch.hann_window(self._win_length).pow(0.5)
        
        # Initialize caches
        self._reset_caches()

    def _reset_caches(self):
        """Reset all caches to initial state."""
        self._conv_cache = np.zeros([2, 1, 16, 16, 33], dtype="float32")
        self._tra_cache = np.zeros([2, 3, 1, 1, 16], dtype="float32")
        self._inter_cache = np.zeros([2, 1, 33, 16], dtype="float32")

    async def start(self, sample_rate: int):
        """Initialize the ONNX runtime session and verify sample rate."""
        self._sample_rate = sample_rate
        if self._sample_rate != 16000:
            logger.warning(f"Model expects 16kHz audio, got {sample_rate}Hz")
            
        try:
            self._session = onnxruntime.InferenceSession(
                self._model_path,
                providers=['CPUExecutionProvider']
            )
            logger.info("GTCRN noise reduction filter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ONNX session: {e}")
            raise

    async def stop(self):
        """Clean up resources."""
        self._session = None
        self._reset_caches()

    async def process_frame(self, frame: FilterControlFrame):
        """Process control frames - can be extended to handle model-specific controls."""
        pass

    async def filter(self, audio: bytes) -> bytes:
        """Apply noise reduction to a single frame of input audio.
        
        Args:
            audio: Raw PCM audio bytes (single frame)
            
        Returns:
            Processed PCM audio bytes
        """
        try:
            # Convert bytes to float32 numpy array
            audio_array = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Convert to torch tensor and compute STFT
            x = torch.from_numpy(audio_array)
            x = torch.stft(
                x, 
                n_fft=self._n_fft,
                hop_length=self._hop_length,
                win_length=self._win_length,
                window=self._window,
                return_complex=False
            )[None]  # Add batch dimension
            
            # Process the frame through the model
            inputs = x.numpy()
            out_frame, self._conv_cache, self._tra_cache, self._inter_cache = \
                self._session.run(
                    [], 
                    {
                        'mix': inputs[..., :1, :],  # Take single frame
                        'conv_cache': self._conv_cache,
                        'tra_cache': self._tra_cache,
                        'inter_cache': self._inter_cache
                    }
                )
            
            # Inverse STFT for single frame
            enhanced = istft(
                out_frame[..., 0] + 1j * out_frame[..., 1],
                n_fft=self._n_fft,
                hop_length=self._hop_length,
                win_length=self._win_length,
                window=np.hanning(self._win_length) ** 0.5
            )
            
            # Convert back to int16 bytes
            enhanced = np.clip(enhanced.squeeze() * 32768.0, -32768, 32767)
            return enhanced.astype(np.int16).tobytes()
            
        except Exception as e:
            logger.error(f"Error in noise reduction: {e}")
            # On error, return original audio
            return audio
