import React, { useState, useEffect, useRef } from 'react';
import { Loader2, Mic, MicOff } from 'lucide-react';
import styles from './VoiceBar.module.css';

interface VoiceStatus {
  listening: boolean;
  wake_word_detected: boolean;
  last_transcript: string;
  last_response: string;
}

interface PipelineResponse {
  transcript: string;
  response_text: string;
  audio_base64: string;
  total_latency_ms: number;
}

function createAudioContext(): AudioContext {
  const audioContextCtor =
    globalThis.AudioContext || (globalThis as typeof globalThis & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  return new audioContextCtor();
}

export const VoiceBar: React.FC = () => {
  const [status, setStatus] = useState<VoiceStatus>({
    listening: false,
    wake_word_detected: false,
    last_transcript: '',
    last_response: '',
  });

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const audioContextRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const resp = await fetch('/api/voice/status');
        const data: VoiceStatus = await resp.json();
        setStatus(data);
        setTranscript(data.last_transcript);
        setResponse(data.last_response);
      } catch (error) {
        console.error('Failed to fetch voice status:', error);
      }
    };

    const interval = setInterval(checkStatus, 500);
    return () => clearInterval(interval);
  }, []);

  const playAudio = (audioBase64: string) => {
    if (!audioContextRef.current) {
      audioContextRef.current = createAudioContext();
    }

    try {
      const binaryString = atob(audioBase64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.codePointAt(i) ?? 0;
      }

      // Decode WAV
      const audioContext = audioContextRef.current;
      audioContext.decodeAudioData(
        bytes.buffer,
        (audioBuffer) => {
          const source = audioContext.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(audioContext.destination);
          source.start(0);
        },
        (error) => {
          console.error('Failed to decode audio:', error);
        }
      );
    } catch (error) {
      console.error('Failed to play audio:', error);
    }
  };

  const handleMicClick = async () => {
    if (isProcessing) return;

    try {
      setIsProcessing(true);

      // Capture audio from microphone
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!audioContextRef.current) {
        audioContextRef.current = createAudioContext();
      }
      const mediaRecorder = new MediaRecorder(stream);
      const audioChunks: Blob[] = [];

      mediaRecorder.ondataavailable = (event) => {
        audioChunks.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());

        const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
        const arrayBuffer = await audioBlob.arrayBuffer();
        const audioBase64 = btoa(String.fromCodePoint(...new Uint8Array(arrayBuffer)));

        try {
          const resp = await fetch('/api/voice/pipeline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              audio_base64: audioBase64,
              sample_rate: 16000,
            }),
          });

          if (resp.ok) {
            const result: PipelineResponse = await resp.json();
            setTranscript(result.transcript);
            setResponse(result.response_text);

            // Play TTS response
            if (result.audio_base64) {
              playAudio(result.audio_base64);
            }
          }
        } catch (error) {
          console.error('Pipeline error:', error);
        } finally {
          setIsProcessing(false);
        }
      };

      mediaRecorder.start();

      // Record for 5 seconds (user can stop earlier by clicking again)
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
      }, 5000);
    } catch (error) {
      console.error('Microphone error:', error);
      setIsProcessing(false);
    }
  };

  const toggleListening = async () => {
    try {
      const endpoint = isListening ? '/api/voice/wake-word/disable' : '/api/voice/wake-word/enable';
      await fetch(endpoint, { method: 'POST' });
      setIsListening(!isListening);
    } catch (error) {
      console.error('Failed to toggle listening:', error);
    }
  };

  let statusLabel = 'Ready';
  if (isProcessing) {
    statusLabel = 'Processing...';
  } else if (isListening) {
    statusLabel = 'Listening';
  }

  return (
    <div className={styles.voiceBar}>
      {/* Transcription bubble */}
      {transcript && (
        <div className={styles.transcriptBubble}>
          <div className={styles.bubbleTitle}>You said:</div>
          <div className={styles.bubbleText}>{transcript}</div>
        </div>
      )}

      {/* Response bubble */}
      {response && (
        <div className={styles.responseBubble}>
          <div className={styles.bubbleTitle}>Kryos:</div>
          <div className={styles.bubbleText}>{response}</div>
        </div>
      )}

      {/* Control bar */}
      <div className={styles.controlBar}>
        {/* Microphone button */}
        <button
          className={`${styles.button} ${isProcessing ? styles.processing : ''}`}
          onClick={handleMicClick}
          disabled={isProcessing}
          title="Click to record (up to 5 seconds)"
        >
          {isProcessing ? (
            <Loader2 size={20} className={styles.waveform} />
          ) : (
            <Mic size={20} />
          )}
        </button>

        {/* Wake word toggle */}
        <button
          className={`${styles.button} ${isListening ? styles.active : ''}`}
          onClick={toggleListening}
          title="Toggle wake word detection"
        >
          {isListening ? <Mic size={20} /> : <MicOff size={20} />}
        </button>

        {/* Status indicator */}
        <div className={styles.statusIndicator}>
          {isProcessing && <div className={styles.spinner} />}
          <span className={styles.statusText}>
            {statusLabel}
          </span>
        </div>
      </div>

      {/* Latency display */}
      {status.last_transcript && (
        <div className={styles.latency}>Ready for voice commands</div>
      )}
    </div>
  );
};
