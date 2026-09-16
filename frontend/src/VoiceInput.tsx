import { useState, useRef, useEffect } from 'react'

interface VoiceInputProps {
  onSend: (text: string) => void
  placeholder?: string
  sendLabel?: string
  disabled?: boolean
}

export default function VoiceInput({ onSend, placeholder = "点击麦克风或直接输入...", sendLabel = "发送", disabled = false }: VoiceInputProps) {
  const [text, setText] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [voiceSupported, setVoiceSupported] = useState(true)
  const [voiceError, setVoiceError] = useState('')
  const recognitionRef = useRef<any>(null)

  useEffect(() => {
    // 检测浏览器是否支持语音识别
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      setVoiceSupported(false)
      return
    }
    const recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true

    recognition.onresult = (event: any) => {
      let finalTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          finalTranscript += transcript
        }
      }
      if (finalTranscript) {
        setText(prev => prev + finalTranscript)
      }
    }

    recognition.onerror = (event: any) => {
      // 如果 Chromium 无法连接 Google 语音服务，自动降级
      if (event.error === 'network' || event.error === 'not-allowed') {
        setVoiceError('当前浏览器语音服务不可用，请手动输入')
        setVoiceSupported(false)
      }
      setIsRecording(false)
    }

    recognition.onend = () => {
      setIsRecording(false)
    }

    recognitionRef.current = recognition
  }, [])

  const toggleRecording = () => {
    if (!voiceSupported) {
      alert(voiceError || '当前浏览器不支持语音识别，请手动输入。')
      return
    }
    if (isRecording) {
      recognitionRef.current?.stop()
      setIsRecording(false)
    } else {
      try {
        recognitionRef.current?.start()
        setIsRecording(true)
        setVoiceError('')
      } catch (e) {
        setVoiceError('录音启动失败，请手动输入')
        setVoiceSupported(false)
      }
    }
  }

  const handleSend = () => {
    if (!text.trim()) return
    if (isRecording) {
      recognitionRef.current?.stop()
      setIsRecording(false)
    }
    onSend(text.trim())
    setText('')
  }

  return (
    <div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '15px', marginBottom: '12px', boxSizing: 'border-box' }}
      />
      {voiceError && (
        <div style={{ fontSize: '12px', color: '#c0392b', marginBottom: '8px' }}>{voiceError}</div>
      )}
      <div style={{ display: 'flex', justifyContent: 'center', gap: '10px' }}>
        <button
          onClick={toggleRecording}
          disabled={disabled || !voiceSupported}
          style={{
            padding: '10px 20px',
            borderRadius: '30px',
            border: 'none',
            background: isRecording ? '#c0392b' : (voiceSupported ? '#8b4513' : '#ccc'),
            color: '#fff',
            fontSize: '15px',
            cursor: voiceSupported ? 'pointer' : 'not-allowed',
            fontFamily: 'serif'
          }}
        >
          {isRecording ? '⏹ 停止录音' : '🎤 开始录音'}
        </button>
        <button
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          style={{
            padding: '10px 24px',
            borderRadius: '30px',
            border: 'none',
            background: text.trim() ? '#5a7d5a' : '#ccc',
            color: '#fff',
            fontSize: '15px',
            cursor: text.trim() ? 'pointer' : 'not-allowed',
            fontFamily: 'serif'
          }}
        >
          {sendLabel}
        </button>
      </div>
      {isRecording && (
        <div style={{ textAlign: 'center', fontSize: '12px', color: '#c0392b', marginTop: '8px' }}>
          ● 正在录音，请说话...
        </div>
      )}
    </div>
  )
}