import { useEffect, useState, useRef } from 'react'

interface HuangliData { date: string; lunar: string; solar_term: string; solar_term_tip: string; health_trend: string; homework: string; }
interface RoleData { role_type: string; name: string; task: string; detail: string; }
interface Transcription { id: number; patient_name: string; content: string; data_type: string; }
interface Draft { id: number; transcript_id: number; patient_name: string; content: string; signed: boolean; doctor?: string; }
interface Patient { name: string; teacher_name: string; guardian_name: string; relation: string; }
interface PatientRecord { id: number; patient_name: string; ai_draft: string; final_plan: string; doctor: string; }
interface PatientProfile { patient_name: string; gender: string; birth_date: string; birth_time: string; birth_place: string; location: string; bazi?: string; wuxing?: string; }
interface Teacher { name: string; description: string; }

export default function App() {
  const [huangli, setHuangli] = useState<HuangliData | null>(null)
  const [currentRole, setCurrentRole] = useState('学生')
  const [roleData, setRoleData] = useState<RoleData | null>(null)
  const [inputText, setInputText] = useState('')
  const [transcriptions, setTranscriptions] = useState<Transcription[]>([])
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [patientRecords, setPatientRecords] = useState<PatientRecord[]>([])
  const [finalPlans, setFinalPlans] = useState<{ [key: number]: string }>({})
  // 【第37天新增】老师端现场记录
  const [liveNote, setLiveNote] = useState<{ [draftId: number]: { tongue: string; pulse: string; notes: string } }>({})
  const [liveUploading, setLiveUploading] = useState<{ [draftId: number]: boolean }>({})
  // 【第33天新增】从病历内容中提取图片URL
  const extractImageUrls = (content: string): string[] => {
    // 【第42天修复】去掉可能的重复，双重保险
    const regex = /\/uploads\/[a-zA-Z0-9._-]+\.(?:jpg|jpeg|png|gif|webp)/g
    const matches = content.match(regex)
    if (!matches) return []
    // 用两次 Set 去重 + 强制去除空字符串
    return Array.from(new Set(matches.filter(m => m && m.length > 5)))
  }
  const extractAudioUrls = (content: string): string[] => {
    const regex = /\/uploads\/audio_[a-zA-Z0-9.]+/g
    const matches = content.match(regex)
    return matches ? Array.from(new Set(matches)) : []
  }
  const [points, setPoints] = useState<{ patient_points: number; teacher_points: number } | null>(null)
  const [patients, setPatients] = useState<Patient[]>([])
  const [selectedPatient, setSelectedPatient] = useState('张三')
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [profile, setProfile] = useState<PatientProfile | null>(null)
  const [healthTrend, setHealthTrend] = useState<any>(null)
  const [dailyAdvice, setDailyAdvice] = useState<any>(null)
  // 【第38天新增】邀请码
  const [invites, setInvites] = useState<any[]>([])
  const [pendingInviteCode, setPendingInviteCode] = useState<string>('')
  // 【第40天新增】录音文件 + 媒体录制器
  const [pendingAudios, setPendingAudios] = useState<string[]>([])
  const [mediaRecorder, setMediaRecorder] = useState<any>(null)
  // 【第39天新增】语音识别
  const [isRecordingStudent, setIsRecordingStudent] = useState(false)
  const [recognitionStudent, setRecognitionStudent] = useState<any>(null)
  // 【第42天重构】老师端现场记录（大段文字 + 录音 + AI整理）
  const [teacherLiveText, setTeacherLiveText] = useState<{ [draftId: number]: string }>({})
  const [teacherLiveRecording, setTeacherLiveRecording] = useState<number | null>(null)
  const [teacherLiveRecognition, setTeacherLiveRecognition] = useState<any>(null)
  const [teacherLiveStructurizing, setTeacherLiveStructurizing] = useState<{ [draftId: number]: boolean }>({})
  const [recognitionTeacher, setRecognitionTeacher] = useState<any>(null)
  const [newStudentNameFromInvite, setNewStudentNameFromInvite] = useState<string>('')
  const [editingProfile, setEditingProfile] = useState(false)
  const [showAddFamily, setShowAddFamily] = useState(false)
  const [newFamilyName, setNewFamilyName] = useState('')
  const [newRelation, setNewRelation] = useState('')
  const [newGender, setNewGender] = useState('')
  const [newBirthYear, setNewBirthYear] = useState('')
  const [newBirthMonth, setNewBirthMonth] = useState('')
  const [newBirthDay, setNewBirthDay] = useState('')
  const [newBirthTime, setNewBirthTime] = useState('')
  const [newBirthPlace, setNewBirthPlace] = useState('')
  const [newLocation, setNewLocation] = useState('')
  const [guardianLocation, setGuardianLocation] = useState('')
  const [guardianGender, setGuardianGender] = useState('')
  const [guardianBirthDate, setGuardianBirthDate] = useState('')

  const [draftProfile, setDraftProfile] = useState<PatientProfile | null>(null)

  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [patientTeachers, setPatientTeachers] = useState<string[]>([])
  const [selectedTeacher, setSelectedTeacher] = useState('李老师')
  const [showTeacherPicker, setShowTeacherPicker] = useState(false)
  const [teacherPatients, setTeacherPatients] = useState<string[]>([])

  // 【第32天】结构化预览 + 待发送图片
  const [structuredPreview, setStructuredPreview] = useState<string | null>(null)
  const [pendingImages, setPendingImages] = useState<string[]>([])

  const now = new Date()
  const currentYear = now.getFullYear()
  const currentMonth = now.getMonth() + 1
  const currentDay = now.getDate()

  const yearOptions = Array.from({ length: currentYear - 1920 + 1 }, (_, i) => currentYear - i)
  const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1).filter(m => {
    if (parseInt(newBirthYear) === currentYear) return m <= currentMonth
    return true
  })
  const getDayOptions = () => {
    const y = parseInt(newBirthYear) || currentYear
    const m = parseInt(newBirthMonth) || 1
    if (y === currentYear && m === currentMonth) {
      return Array.from({ length: currentDay }, (_, i) => i + 1)
    }
    const days = new Date(y, m, 0).getDate()
    return Array.from({ length: days }, (_, i) => i + 1)
  }

  const timeOptions = [
    { value: "", label: "时辰未知（选填）" },
    { value: "23:00", label: "子时 (23:00-01:00)" },
    { value: "01:00", label: "丑时 (01:00-03:00)" },
    { value: "03:00", label: "寅时 (03:00-05:00)" },
    { value: "05:00", label: "卯时 (05:00-07:00)" },
    { value: "07:00", label: "辰时 (07:00-09:00)" },
    { value: "09:00", label: "巳时 (09:00-11:00)" },
    { value: "11:00", label: "午时 (11:00-13:00)" },
    { value: "13:00", label: "未时 (13:00-15:00)" },
    { value: "15:00", label: "申时 (15:00-17:00)" },
    { value: "17:00", label: "酉时 (17:00-19:00)" },
    { value: "19:00", label: "戌时 (19:00-21:00)" },
    { value: "21:00", label: "亥时 (21:00-23:00)" }
  ]

  useEffect(() => {
    fetch('/api/huangli').then(r => r.json()).then(d => setHuangli(d)).catch(() => setHuangli(null))
    // 【第38天新增】检查 URL 里是否有邀请码
    const urlParams = new URLSearchParams(window.location.search)
    const inviteCode = urlParams.get('invite')
    if (inviteCode) {
      setPendingInviteCode(inviteCode)
    }
    fetch('/api/teachers').then(r => r.json()).then(d => setTeachers(d)).catch(() => setTeachers([]))
    fetchPatients('张三')
    fetch('/api/patient-profile?patient_name=张三')
      .then(r => r.json())
      .then(d => {
        setGuardianLocation(d.location || '')
        setGuardianGender(d.gender || '')
        setGuardianBirthDate(d.birth_date || '')
      })
      .catch(() => { })
  }, [])

  useEffect(() => {
    fetch(`/api/patient-teachers?patient_name=${selectedPatient}`)
      .then(r => r.json())
      .then((list: string[]) => {
        setPatientTeachers(list)
        if (list.length > 0) setSelectedTeacher(list[0])
      })
      .catch(() => setPatientTeachers([]))
  }, [selectedPatient])

  useEffect(() => {
    if (currentRole === '李老师' || currentRole === '李老师智能体') {
      fetch(`/api/teacher-patients?teacher_name=${selectedTeacher}`)
        .then(r => r.json())
        .then(d => setTeacherPatients(d))
        .catch(() => setTeacherPatients([]))
    }
  }, [currentRole, selectedTeacher])

  const fetchPatients = (guardian: string) => {
    fetch(`/api/patients?guardian_name=${guardian}`).then(r => r.json()).then(d => setPatients(d)).catch(() => setPatients([]))
  }

  const fetchRoleData = () => {
    fetch(`/api/role-data?role=${currentRole}&patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => setRoleData(d)).catch(() => setRoleData(null))
  }

  const fetchTranscriptions = () => {
    fetch(`/api/transcriptions?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => setTranscriptions(d)).catch(() => setTranscriptions([]))
  }

  const fetchDrafts = () => {
    fetch(`/api/drafts?teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => setDrafts(d)).catch(() => setDrafts([]))
  }

  const fetchPatientRecords = () => {
    fetch(`/api/patient-records?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => {
        const sorted = d.sort((a: any, b: any) => b.id - a.id)
        setPatientRecords(sorted)
      }).catch(() => setPatientRecords([]))
  }

  const fetchPoints = () => {
    fetch(`/api/points?patient_name=${selectedPatient}`).then(r => r.json()).then(d => setPoints(d)).catch(() => setPoints(null))
  }

  const fetchProfile = () => {
    fetch(`/api/patient-profile?patient_name=${selectedPatient}`).then(r => r.json()).then(d => setProfile(d)).catch(() => setProfile(null))
  }
  const fetchHealthTrend = () => {
    console.log('fetchHealthTrend 被调用了, patient=', selectedPatient)
    fetch(`/api/health-trend?patient_name=${selectedPatient}`)
      .then(r => r.json())
      .then(d => {
        console.log('health-trend 返回:', d)
        setHealthTrend(d && !d.error ? d : null)
      })
      .catch(e => { console.log('health-trend 出错:', e); setHealthTrend(null) })
  }

  const fetchDailyAdvice = () => {
    fetch(`/api/daily-advice?patient_name=${selectedPatient}`)
      .then(r => r.json())
      .then(d => setDailyAdvice(d && !d.error ? d : null))
      .catch(() => setDailyAdvice(null))
  }

  const fetchInvites = () => {
    fetch(`/api/invites?teacher_name=${selectedTeacher}`)
      .then(r => r.json())
      .then(d => setInvites(d))
      .catch(() => setInvites([]))
  }

  const handleCreateInvite = () => {
    fetch('/api/invites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher })
    })
      .then(r => r.json())
      .then(d => {
        if (d.code) {
          fetchInvites()
          alert(`邀请码已生成：${d.code}\n可复制链接发给学生。`)
        }
      })
  }

  const getInviteLink = (code: string) => {
    const base = window.location.origin
    return `${base}/?invite=${code}`
  }

  const handleCopyInviteLink = (code: string) => {
    const link = getInviteLink(code)
    navigator.clipboard.writeText(link).then(() => {
      alert(`已复制邀请链接：\n${link}`)
    }).catch(() => {
      alert(`请手动复制链接：\n${link}`)
    })
  }

  const handleAcceptInvite = () => {
    if (!newStudentNameFromInvite.trim()) {
      alert("请输入您的姓名")
      return
    }
    fetch('/api/invites/accept', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: pendingInviteCode, student_name: newStudentNameFromInvite.trim() })
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) { alert(d.error); return }
        alert(`欢迎加入！您已加入 ${d.teacher_name} 的学习小组。`)
        setPendingInviteCode('')
        setNewStudentNameFromInvite('')
        fetchPatients('张三')
        // 重新加载页面，让 URL 参数生效
        window.history.replaceState({}, '', '/')
        window.location.reload()
      })
  }

  const startStudentRecording = async () => {
    if (isRecordingStudent) {
      // 停止录音
      mediaRecorder?.stop()
      recognitionStudent?.stop()
      setIsRecordingStudent(false)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const chunks: Blob[] = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }

      recorder.onstop = async () => {
        // 上传音频文件
        const blob = new Blob(chunks, { type: 'audio/webm' })
        const formData = new FormData()
        formData.append('file', blob, 'recording.webm')
        try {
          const r = await fetch('/api/upload-audio', { method: 'POST', body: formData })
          const d = await r.json()
          if (d.url) setPendingAudios(prev => [...prev, d.url])
        } catch (e) {
          console.error('音频上传失败', e)
        }
        stream.getTracks().forEach(t => t.stop())
      }

      // Web Speech 只取 isFinal 结果，避免重复
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (SR) {
        const rec = new SR()
        rec.continuous = true
        rec.interimResults = false  // 【关键改动】只要最终结果，不要 interim
        rec.lang = 'zh-CN'
        rec.onresult = (event: any) => {
          let finalTranscript = ''
          for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) {
              finalTranscript += event.results[i][0].transcript
            }
          }
          if (finalTranscript) {
            setInputText(prev => prev + finalTranscript)
          }
        }
        rec.onerror = (e: any) => console.error('语音识别错误:', e)
        rec.start()
        setRecognitionStudent(rec)
      }

      recorder.start()
      setMediaRecorder(recorder)
      setIsRecordingStudent(true)
    } catch (e) {
      alert("无法访问麦克风，请检查浏览器权限。")
    }
  }

  // 【第42天重构】老师端录音：只听写，不上传音频，转完就丢
  const startTeacherLiveRecording = (draftId: number) => {
    if (teacherLiveRecording === draftId) {
      teacherLiveRecognition?.stop()
      setTeacherLiveRecording(null)
      return
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) {
      alert("当前浏览器不支持语音识别。请使用最新版 Chrome 或 Edge 浏览器。")
      return
    }
    const rec = new SR()
    rec.continuous = true
    rec.interimResults = false
    rec.lang = 'zh-CN'
    rec.onresult = (event: any) => {
      let finalTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript
        }
      }
      if (finalTranscript) {
        setTeacherLiveText(prev => ({ ...prev, [draftId]: (prev[draftId] || '') + finalTranscript }))
      }
    }
    rec.onerror = () => setTeacherLiveRecording(null)
    rec.onend = () => setTeacherLiveRecording(null)
    rec.start()
    setTeacherLiveRecognition(rec)
    setTeacherLiveRecording(draftId)
  }

  // 【第42天新增】老师端 AI 整理
  const handleTeacherStructurize = (draftId: number) => {
    const raw = teacherLiveText[draftId]
    if (!raw || !raw.trim()) {
      alert("请先录音或输入内容")
      return
    }
    setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: true }))
    fetch('/api/teacher-structurize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: raw })
    })
      .then(r => r.json())
      .then(d => {
        setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: false }))
        if (d.structured) {
          setTeacherLiveText(prev => ({ ...prev, [draftId]: d.structured }))
        }
      })
      .catch(() => {
        setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: false }))
        alert("AI 整理失败，请重试")
      })
  }

  // 【第42天新增】追加到病历草案
  const handleAppendTeacherNote = (draftId: number) => {
    const text = teacherLiveText[draftId]
    if (!text || !text.trim()) {
      alert("请先录音或输入内容")
      return
    }
    const draft = drafts.find(x => x.id === draftId)
    if (draft) {
      const newContent = draft.content + '\n\n【现场记录】\n' + text
      handleEditDraft(draftId, newContent)
      setTeacherLiveText(prev => ({ ...prev, [draftId]: '' }))
    }
  }
  rec.onerror = (e: any) => {
    console.error('语音识别错误:', e)
    setIsRecordingTeacher(null)
  }
  rec.onend = () => setIsRecordingTeacher(null)
  rec.start()
  setRecognitionTeacher(rec)
  setIsRecordingTeacher({ draftId, field })
}

useEffect(() => {
  fetchRoleData()
  fetchTranscriptions()
  fetchDrafts()
  fetchPatientRecords()
  fetchPoints()
  fetchProfile()
  fetchHealthTrend()
  fetchDailyAdvice()
  setShowHistory(false)
}, [currentRole, selectedPatient, selectedTeacher])

const handleCheckIn = () => {
  fetch(`/api/check-in?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`, { method: 'POST' }).then(() => {
    fetchRoleData()
    fetchPoints()
  })
}

const handleApprove = () => { fetch(`/api/approve?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`, { method: 'POST' }).then(() => fetchRoleData()) }

// 【第32天】整理成结构化陈述（把文字 + 待发送图片一起预览）
const handleTranscribe = () => {
  if (!inputText.trim() && pendingImages.length === 0 && pendingAudios.length === 0) {
    alert("请先输入文字、录音或上传图片")
    return
  }
  // 调用患者端智能体做结构化整理
  fetch('/api/patient-structurize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patient_name: selectedPatient, raw_text: inputText })
  })
    .then(r => r.json())
    .then(d => {
      // 【第41天修复】预览里不拼 URL，只提示附件数量
      const attachmentNote = []
      if (pendingImages.length > 0) attachmentNote.push(`${pendingImages.length} 张图片`)
      if (pendingAudios.length > 0) attachmentNote.push(`${pendingAudios.length} 段录音`)
      const attachText = attachmentNote.length > 0 ? `\n\n（本次将随附：${attachmentNote.join('、')}）` : ''
      const preview = `【学生自述】\n学生姓名：${selectedPatient}\n就诊时间：${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日\n\n${d.structured}${attachText}\n\n（以上内容已经过学生智能体整理，待学生确认后发送给老师）`
      setStructuredPreview(preview)
    })
    .catch(() => {
      // 降级：本地拼接
      const preview = `【学生自述】\n学生姓名：${selectedPatient}\n就诊时间：${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日\n主诉内容：${inputText}\n\n（以上为学生原话转述，未经智能体推断）`
      setStructuredPreview(preview)
    })
}

// 【第32天】确认发送：先发文字，再逐张发图片，最后清空所有待发送内容
const handleConfirmSend = async () => {
  if (!structuredPreview) return

  // 【第41天修复】把所有内容拼成一段，只发一次
  const imagePart = pendingImages.length > 0
    ? '\n\n【学生上传的图片】\n' + pendingImages.map((url, i) => `图片${i + 1}：${url}`).join('\n')
    : ''
  const audioPart = pendingAudios.length > 0
    ? '\n\n【学生上传的录音】\n' + pendingAudios.map((url, i) => `录音${i + 1}：${url}`).join('\n')
    : ''

  const fullContent = structuredPreview + imagePart + audioPart

  await fetch('/api/transcribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      patient_name: selectedPatient,
      teacher_name: selectedTeacher,
      content: fullContent,
      data_type: 'text'
    })
  })

  // 清空所有待发送内容
  setInputText('')
  setPendingImages([])
  setPendingAudios([])
  setStructuredPreview(null)
  fetchTranscriptions()
  fetchDrafts()
}

// 【第32天】图片上传只是临时存储，加入待发送列表
const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0]
  if (!file) return
  setUploading(true)
  const formData = new FormData()
  formData.append('file', file)
  fetch(`/api/upload-temp`, { method: 'POST', body: formData })
    .then(r => r.json())
    .then(d => {
      setUploading(false)
      setPendingImages(prev => [...prev, d.url])
      if (fileInputRef.current) fileInputRef.current.value = ''
    })
    .catch(() => {
      setUploading(false)
      alert("图片上传失败，请重试")
    })
}

// 【第32天】删除待发送的图片
const handleRemovePendingImage = (url: string) => {
  setPendingImages(prev => prev.filter(u => u !== url))
}

const handleEditDraft = (draftId: number, newContent: string) => {
  fetch(`/api/drafts/${draftId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: newContent })
  }).then(() => fetchDrafts())
}

// 【第37天新增】现场拍照上传，URL 追加到病历草案
const handleLivePhotoUpload = (draftId: number, e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0]
  if (!file) return
  setLiveUploading(prev => ({ ...prev, [draftId]: true }))
  const formData = new FormData()
  formData.append('file', file)
  fetch('/api/upload-temp', { method: 'POST', body: formData })
    .then(r => r.json())
    .then(d => {
      // 把图片 URL 追加到病历草案
      const draft = drafts.find(x => x.id === draftId)
      if (draft) {
        const newContent = draft.content + `\n\n【现场照片】\n[老师现场拍摄：${d.url}]`
        handleEditDraft(draftId, newContent)
      }
      setLiveUploading(prev => ({ ...prev, [draftId]: false }))
    })
    .catch(() => {
      setLiveUploading(prev => ({ ...prev, [draftId]: false }))
      alert("照片上传失败")
    })
}


const handleSignDraft = (draftId: number) => {
  const plan = finalPlans[draftId]?.trim()
  if (!plan) {
    alert("请先填写给学生的最终辨证施治方案！")
    return
  }
  fetch(`/api/drafts/${draftId}/sign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ final_plan: plan })
  }).then(() => {
    fetchDrafts();
    fetchPatientRecords();
    fetchPoints();
    setFinalPlans(prev => ({ ...prev, [draftId]: '' }));
  })
}

const handleSaveProfile = () => {
  if (!draftProfile) return
  fetch('/api/patient-profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draftProfile)
  }).then(() => {
    setEditingProfile(false)
    fetchProfile()
  })
}

const handleRelationChange = (value: string) => {
  setNewRelation(value)
  if (['父亲', '儿子'].includes(value)) {
    setNewGender('男')
  } else if (['母亲', '女儿'].includes(value)) {
    setNewGender('女')
  } else if (value === '配偶') {
    if (guardianGender === '男') {
      setNewGender('女')
    } else if (guardianGender === '女') {
      setNewGender('男')
    } else {
      setNewGender('')
      alert("提示：请先填写您的性别，系统将自动推导配偶性别。")
    }
  } else {
    setNewGender('')
  }
}

const handleToggleAddFamily = () => {
  if (!showAddFamily) {
    setNewLocation(guardianLocation)
    setNewBirthPlace(guardianLocation)
  }
  setShowAddFamily(!showAddFamily)
}

const handleAddFamily = () => {
  if (patients.length >= 5) {
    alert("最多只能添加 5 位家庭成员（含本人），请先删除不再需要的家属档案。")
    return
  }
  if (!newFamilyName.trim() || !newRelation.trim() || !newGender || !newBirthYear || !newBirthMonth || !newBirthDay) {
    alert("请至少填写姓名、关系、性别和完整的出生年月日！")
    return
  }
  if (patients.some(p => p.name === newFamilyName.trim())) {
    alert(`家属【${newFamilyName.trim()}】已存在，请勿重复添加。`)
    return
  }
  if (['父亲', '母亲'].includes(newRelation) && guardianBirthDate) {
    const mm = String(newBirthMonth).padStart(2, '0')
    const dd = String(newBirthDay).padStart(2, '0')
    const familyDate = `${newBirthYear}-${mm}-${dd}`
    if (familyDate >= guardianBirthDate) {
      alert(`【${newRelation}】的出生日期应早于您的出生日期，请检查。`)
      return
    }
  }

  const mm = String(newBirthMonth).padStart(2, '0')
  const dd = String(newBirthDay).padStart(2, '0')
  const birthDate = `${newBirthYear}-${mm}-${dd}`

  fetch('/api/patients/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: newFamilyName, guardian_name: '张三', relation: newRelation,
      gender: newGender, birth_date: birthDate, birth_time: newBirthTime,
      birth_place: newBirthPlace, location: newLocation
    })
  }).then(() => {
    setNewFamilyName(''); setNewRelation(''); setNewGender('')
    setNewBirthYear(''); setNewBirthMonth(''); setNewBirthDay('')
    setNewBirthTime(''); setNewBirthPlace(''); setNewLocation('')
    setShowAddFamily(false)
    fetchPatients('张三')
  })
}

const handleDeleteFamily = (name: string) => {
  if (name === '张三') { alert("本人档案不可删除！"); return }
  if (!confirm(`确定要删除亲友【${name}】吗？删除后将无法恢复。`)) return
  fetch(`/api/patients/${name}`, { method: 'DELETE' }).then(() => {
    if (selectedPatient === name) setSelectedPatient('张三')
    fetchPatients('张三')
  })
}

const handleAddTeacher = (teacherName: string) => {
  fetch('/api/patient-teachers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ patient_name: selectedPatient, teacher_name: teacherName })
  }).then(r => r.json()).then(d => {
    if (d.error) { alert(d.error); return }
    fetch(`/api/patient-teachers?patient_name=${selectedPatient}`)
      .then(r => r.json()).then((list: string[]) => setPatientTeachers(list))
  })
}

const handleRemoveTeacher = (teacherName: string) => {
  if (!confirm(`确定要退出老师【${teacherName}】的咨询吗？`)) return
  fetch(`/api/patient-teachers?patient_name=${selectedPatient}&teacher_name=${teacherName}`, { method: 'DELETE' })
    .then(() => {
      fetch(`/api/patient-teachers?patient_name=${selectedPatient}`)
        .then(r => r.json()).then((list: string[]) => {
          setPatientTeachers(list)
          if (selectedTeacher === teacherName && list.length > 0) setSelectedTeacher(list[0])
        })
    })
}

const boxStyle = { background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '24px', marginBottom: '20px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }
const roleBtnStyle = (role: string) => ({ padding: '8px 16px', margin: '5px', borderRadius: '20px', border: '1px solid #8b4513', cursor: 'pointer', fontFamily: 'serif', fontSize: '14px', backgroundColor: currentRole === role ? '#8b4513' : '#fdfcf0', color: currentRole === role ? '#fff' : '#8b4513', transition: 'all 0.2s' })
const patientBtnStyle = (name: string) => ({ padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px solid #5a7d5a', cursor: 'pointer', fontFamily: 'serif', fontSize: '13px', backgroundColor: selectedPatient === name ? '#5a7d5a' : '#f7fcf9', color: selectedPatient === name ? '#fff' : '#5a7d5a', transition: 'all 0.2s' })
const teacherBtnStyle = (name: string) => ({ padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px solid #8b4513', cursor: 'pointer', fontFamily: 'serif', fontSize: '13px', backgroundColor: selectedTeacher === name ? '#8b4513' : '#fdfcf0', color: selectedTeacher === name ? '#fff' : '#8b4513', transition: 'all 0.2s' })
const inputStyle = { width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '8px', boxSizing: 'border-box' as const }
const dateSelectStyle = { padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginRight: '6px', marginBottom: '8px' }

const needGender = !profile?.gender
const needBirthDate = !profile?.birth_date
const needBirthTime = !profile?.birth_time
const needBirthPlace = !profile?.birth_place

return (
  <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '40px 20px', fontFamily: 'serif' }}>
    <div style={{ maxWidth: '600px', margin: '0 auto' }}>
      {/* 【第38天新增】接受邀请弹窗 */}
      {pendingInviteCode && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
          <div style={{ background: '#fdfcf0', padding: '24px', borderRadius: '12px', maxWidth: '400px', width: '90%', border: '2px solid #8b4513' }}>
            <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px', textAlign: 'center' }}>🎫 接受老师邀请</div>
            <div style={{ fontSize: '13px', color: '#666', marginBottom: '15px', textAlign: 'center' }}>
              邀请码：<span style={{ fontFamily: 'monospace', color: '#8b4513', fontWeight: 'bold' }}>{pendingInviteCode}</span>
            </div>
            <input
              placeholder="请输入您的姓名"
              value={newStudentNameFromInvite}
              onChange={e => setNewStudentNameFromInvite(e.target.value)}
              style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '14px', marginBottom: '15px', boxSizing: 'border-box' }}
            />
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => { setPendingInviteCode(''); window.history.replaceState({}, '', '/') }}
                style={{ flex: 1, padding: '10px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer' }}
              >取消</button>
              <button
                onClick={handleAcceptInvite}
                style={{ flex: 1, padding: '10px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}
              >加入</button>
            </div>
          </div>
        </div>
      )}

      <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px', fontSize: '28px', letterSpacing: '2px' }}>知衡 · 中医治未病社区</h1>

      {huangli && (
        <div style={boxStyle}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#333', marginBottom: '5px' }}>
            <span style={{ fontWeight: 'bold' }}>{huangli.date}</span> · {huangli.lunar}
          </div>
          {huangli.solar_term_tip && huangli.solar_term_tip !== '无' && (
            <div style={{ textAlign: 'center', color: '#8b4513', fontSize: '14px', marginBottom: '15px' }}>
              🌿 {huangli.solar_term_tip}
            </div>
          )}
          <div style={{ textAlign: 'center', color: '#5a7d5a', fontSize: '16px', marginBottom: '10px' }}>
            🌿 {huangli.solar_term}：{huangli.health_trend}
          </div>
          <div style={{ textAlign: 'center', background: '#fff8e7', padding: '15px', borderRadius: '8px', color: '#8b4513' }}>
            📝 今日作业：{huangli.homework}
          </div>
        </div>
      )}
        {/* 【第36天】健康趋势卡片 */}
        {(currentRole === '学生' || currentRole === '学生智能体') && healthTrend && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>📊 我的健康趋势</div>
            <div style={{ textAlign: 'center', fontSize: '13px', color: '#666', marginBottom: '12px' }}>
              八字：{healthTrend.bazi}
            </div>

            {/* 五行分布 */}
            <div style={{ marginBottom: '15px' }}>
              <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>五行分布：</div>
              {(['木', '火', '土', '金', '水'] as const).map((el) => {
                const count = healthTrend.counts[el]
                const barWidth = Math.min(count * 20, 100)
                const isWeakest = el === healthTrend.weakest
                return (
                  <div key={el} style={{ display: 'flex', alignItems: 'center', marginBottom: '6px' }}>
                    <div style={{ width: '30px', fontSize: '14px', color: isWeakest ? '#c0392b' : '#333', fontWeight: isWeakest ? 'bold' : 'normal' }}>{el}</div>
                    <div style={{ flex: 1, height: '16px', background: '#f0f0f0', borderRadius: '8px', overflow: 'hidden', margin: '0 8px' }}>
                      <div style={{
                        width: `${barWidth}%`,
                        height: '100%',
                        background: isWeakest ? '#c0392b' : '#8b4513',
                        borderRadius: '8px',
                        transition: 'width 0.5s'
                      }} />
                    </div>
                    <div style={{ width: '20px', fontSize: '13px', color: '#666', textAlign: 'right' }}>{count}</div>
                  </div>
                )
              })}
            </div>

            {/* 阴阳 */}
            <div style={{ textAlign: 'center', padding: '10px', background: '#fff8e7', borderRadius: '8px', marginBottom: '12px' }}>
              <span style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold' }}>☯ 阴阳状态：{healthTrend.yinyang}</span>
            </div>

            {/* 体质倾向 */}
            <div style={{ padding: '12px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
              <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '5px' }}>💡 体质参考：</div>
              <div style={{ fontSize: '14px', color: '#333', lineHeight: '1.6' }}>{healthTrend.tendency}</div>
            </div>

            <div style={{ textAlign: 'center', fontSize: '11px', color: '#999', marginTop: '10px', fontStyle: 'italic' }}>
              基于出生八字的先天体质参考，具体辨证请以老师当面问诊为准
            </div>
          </div>
        )}
      {/* 【第36天】今日宜忌建议 */}
      {(currentRole === '学生' || currentRole === '学生智能体') && dailyAdvice && (
        <div style={boxStyle}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>🌤️ 今日建议 · {dailyAdvice.solar_term}</div>

          {dailyAdvice.tendency_note && (
            <div style={{ textAlign: 'center', padding: '8px', background: '#fff8e7', borderRadius: '8px', marginBottom: '15px', fontSize: '13px', color: '#8b4513' }}>
              💡 {dailyAdvice.tendency_note}
            </div>
          )}

          <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
            <div style={{ flex: 1, padding: '12px', background: '#f0f7f0', borderRadius: '8px' }}>
              <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '6px' }}>🥗 宜食</div>
              <div style={{ fontSize: '13px', color: '#333', lineHeight: '1.6' }}>{dailyAdvice.eat}</div>
            </div>
            <div style={{ flex: 1, padding: '12px', background: '#fdf0f0', borderRadius: '8px' }}>
              <div style={{ fontSize: '14px', color: '#c0392b', fontWeight: 'bold', marginBottom: '6px' }}>🚫 忌口</div>
              <div style={{ fontSize: '13px', color: '#333', lineHeight: '1.6' }}>{dailyAdvice.avoid}</div>
            </div>
          </div>

          <div style={{ padding: '12px', background: '#f0f4f8', borderRadius: '8px' }}>
            <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '6px' }}>👕 衣着起居</div>
            <div style={{ fontSize: '13px', color: '#333', lineHeight: '1.6' }}>{dailyAdvice.wear}</div>
          </div>
        </div>
      )}

      {(currentRole === '学生' || currentRole === '学生智能体') && (
        <div style={{ ...boxStyle, background: '#fdf8f0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>🧑‍⚕️ 我的老师（{patientTeachers.length}/3）</div>
          </div>
          <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>
            当前咨询：<span style={{ color: '#8b4513', fontWeight: 'bold' }}>{selectedTeacher}</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap' }}>
            {patientTeachers.map(t => (
              <div key={t} style={{ display: 'flex', alignItems: 'center', margin: '4px' }}>
                <button style={teacherBtnStyle(t)} onClick={() => setSelectedTeacher(t)}>👨‍⚕️ {t}</button>
                {patientTeachers.length > 1 && (
                  <button onClick={() => handleRemoveTeacher(t)} style={{ marginLeft: '4px', padding: '2px 8px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>✕</button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {(currentRole === '李老师' || currentRole === '李老师智能体') && (
        <div style={{ ...boxStyle, background: '#f0f7f0' }}>
          <div style={{ fontSize: '18px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>👥 学生管理（{teacherPatients.length}人）</div>

          {/* 添加学生 */}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '15px' }}>
            <input
              id="newStudentInput"
              placeholder="输入学生姓名，添加为新学生"
              style={{ flex: 1, padding: '8px', borderRadius: '6px', border: '1px solid #b8d8c0', fontFamily: 'serif' }}
            />
            <button
              onClick={() => {
                const input = document.getElementById('newStudentInput') as HTMLInputElement
                const name = input?.value.trim()
                if (!name) { alert("请输入学生姓名"); return }
                fetch('/api/teacher/add-student', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ teacher_name: selectedTeacher, student_name: name })
                }).then(() => {
                  input.value = ''
                  fetch(`/api/teacher-patients?teacher_name=${selectedTeacher}`)
                    .then(r => r.json()).then(d => setTeacherPatients(d))
                  fetchPatients('张三')
                })
              }}
              style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer' }}
            >+ 添加学生</button>
            <button
              onClick={handleCreateInvite}
              style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer' }}
            >🎫 生成邀请码</button>
          </div>

          {/* 【第38天新增】邀请码列表 */}
          {invites.length > 0 && (
            <div style={{ marginBottom: '15px', padding: '10px', background: '#fef8f0', borderRadius: '8px', border: '1px dashed #d4c8a8' }}>
              <div style={{ fontSize: '13px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>📮 已生成的邀请码（7天有效）</div>
              {invites.map((inv: any) => (
                <div key={inv.code} style={{ display: 'flex', alignItems: 'center', padding: '6px', background: '#fff', borderRadius: '6px', marginBottom: '5px', fontSize: '13px' }}>
                  <div style={{ flex: 1, color: '#8b4513', fontWeight: 'bold', fontFamily: 'monospace' }}>{inv.code}</div>
                  <div style={{ flex: 1, fontSize: '11px', color: '#999' }}>
                    {inv.used_by ? `已使用：${inv.used_by}` : '未使用'}
                  </div>
                  {!inv.used_by && (
                    <button
                      onClick={() => handleCopyInviteLink(inv.code)}
                      style={{ padding: '3px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '11px' }}
                    >复制链接</button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* 学生花名册 */}
          <div style={{ background: '#fff', borderRadius: '8px', border: '1px solid #d4e8d4', overflow: 'hidden' }}>
            <div style={{ display: 'flex', padding: '10px', background: '#e8f4e8', fontSize: '13px', fontWeight: 'bold', color: '#5a7d5a' }}>
              <div style={{ flex: 2 }}>学生姓名</div>
              <div style={{ flex: 1, textAlign: 'center' }}>状态</div>
              <div style={{ flex: 1, textAlign: 'right' }}>操作</div>
            </div>
            {teacherPatients.length === 0 ? (
              <div style={{ padding: '20px', textAlign: 'center', color: '#999', fontSize: '13px' }}>暂无学生，请在上方添加</div>
            ) : (
              teacherPatients.map(name => (
                <div key={name} style={{ display: 'flex', alignItems: 'center', padding: '10px', borderTop: '1px solid #f0f0f0', fontSize: '14px' }}>
                  <div style={{ flex: 2, color: '#333' }}>👤 {name}</div>
                  <div style={{ flex: 1, textAlign: 'center' }}>
                    <span style={{ padding: '2px 10px', borderRadius: '12px', fontSize: '12px', background: '#e8f4e8', color: '#5a7d5a' }}>活跃</span>
                  </div>
                  <div style={{ flex: 1, textAlign: 'right' }}>
                    <button style={{ padding: '4px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '12px', marginRight: '6px' }}
                      onClick={() => setSelectedPatient(name)}>查看</button>
                    {name !== '张三' && name !== '李四' && (
                      <button
                        onClick={() => {
                          if (!confirm(`确定要将学生【${name}】从您的名单中移除吗？`)) return
                          fetch(`/api/patient-teachers?patient_name=${name}&teacher_name=${selectedTeacher}`, { method: 'DELETE' })
                            .then(() => {
                              fetch(`/api/teacher-patients?teacher_name=${selectedTeacher}`)
                                .then(r => r.json()).then(d => setTeacherPatients(d))
                            })
                        }}
                        style={{ padding: '4px 10px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '12px' }}
                      >移除</button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
          <div style={{ fontSize: '12px', color: '#999', marginTop: '10px', fontStyle: 'italic' }}>
            💡 未来将支持：沉默超期自动标记、欠费提醒、智能体催收建议
          </div>
        </div>
      )}

      {(currentRole === '学生' || currentRole === '学生智能体') && (
        <div style={{ ...boxStyle, background: '#f0f7f5' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div style={{ fontSize: '18px', color: '#5a7d5a', fontWeight: 'bold' }}>🏠 我的家庭（{patients.length}人）</div>
            <button onClick={handleToggleAddFamily} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '12px' }}>
              {showAddFamily ? '取消' : '+ 添加亲友'}
            </button>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
            {patients.map(p => (
              <div key={p.name} style={{ display: 'flex', alignItems: 'center', margin: '4px' }}>
                <button style={patientBtnStyle(p.name)} onClick={() => setSelectedPatient(p.name)}>
                  {p.relation === '本人' ? `👤 ${p.name}` : `👨‍👩‍👧 ${p.name}（${p.relation}）`}
                </button>
                {p.relation !== '本人' && (
                  <button onClick={() => handleDeleteFamily(p.name)} style={{ marginLeft: '4px', padding: '2px 8px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>✕</button>
                )}
              </div>
            ))}
          </div>

          {showAddFamily && (
            <div style={{ marginTop: '15px', borderTop: '1px dashed #b8d8c0', paddingTop: '15px' }}>
              <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>📝 亲友基础信息</div>
              <input value={newFamilyName} onChange={(e) => setNewFamilyName(e.target.value)} placeholder="姓名（必填）" style={inputStyle} />
              <select value={newRelation} onChange={(e) => handleRelationChange(e.target.value)} style={inputStyle}>
                <option value="">与您的关系（必填）</option>
                <option value="父亲">父亲</option>
                <option value="母亲">母亲</option>
                <option value="儿子">儿子</option>
                <option value="女儿">女儿</option>
                <option value="配偶">配偶</option>
                <option value="其他">其他</option>
              </select>
              <select value={newGender} onChange={(e) => setNewGender(e.target.value)} style={inputStyle}>
                <option value="">性别（必填，选关系后自动联动）</option>
                <option value="男">男</option>
                <option value="女">女</option>
              </select>
              <label style={{ fontSize: '12px', color: '#888' }}>出生日期（按 年-月-日 顺序选择）</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: '8px' }}>
                <select value={newBirthYear} onChange={(e) => setNewBirthYear(e.target.value)} style={dateSelectStyle}>
                  <option value="">年</option>
                  {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
                <select value={newBirthMonth} onChange={(e) => setNewBirthMonth(e.target.value)} style={dateSelectStyle}>
                  <option value="">月</option>
                  {monthOptions.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
                <select value={newBirthDay} onChange={(e) => setNewBirthDay(e.target.value)} style={dateSelectStyle}>
                  <option value="">日</option>
                  {getDayOptions().map(d => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <label style={{ fontSize: '12px', color: '#888' }}>出生时间（选填，精确到时辰即可）</label>
              <select value={newBirthTime} onChange={(e) => setNewBirthTime(e.target.value)} style={inputStyle}>
                {timeOptions.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <label style={{ fontSize: '12px', color: '#888' }}>出生地（选填）</label>
              <input value={newBirthPlace} onChange={(e) => setNewBirthPlace(e.target.value)} placeholder="例如：浙江省绍兴市" style={inputStyle} />
              <label style={{ fontSize: '12px', color: '#888' }}>现居住地（默认继承您的居住地）</label>
              <input value={newLocation} onChange={(e) => setNewLocation(e.target.value)} placeholder="例如：广东省广州市" style={inputStyle} />
              <div style={{ textAlign: 'right', marginTop: '10px' }}>
                <button onClick={handleAddFamily} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer' }}>确认添加亲友</button>
              </div>
            </div>
          )}
        </div>
      )}

      {(currentRole === '学生' || currentRole === '学生智能体') && profile && (
        <div style={{ ...boxStyle, background: '#fffaf0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
            <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>📋 {selectedPatient} 的基础档案</div>
            {editingProfile ? (
              <div>
                <button onClick={() => setEditingProfile(false)} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px', marginRight: '6px' }}>取消</button>
                <button onClick={handleSaveProfile} style={{ padding: '4px 12px', borderRadius: '15px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '12px' }}>保存档案</button>
              </div>
            ) : (
              <button onClick={() => { setDraftProfile({ ...profile }); setEditingProfile(true) }} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px' }}>编辑/补充</button>
            )}
          </div>

          {editingProfile && draftProfile ? (
            <div>
              <label style={{ fontSize: '13px', color: '#666' }}>性别</label>
              {needGender ? (
                <select value={draftProfile.gender} onChange={e => setDraftProfile({ ...draftProfile, gender: e.target.value })} style={inputStyle}>
                  <option value="">请选择</option>
                  <option value="男">男</option>
                  <option value="女">女</option>
                </select>
              ) : (<div style={{ fontSize: '14px', color: '#333', marginBottom: '8px' }}>{profile.gender}</div>)}

              <label style={{ fontSize: '13px', color: '#666' }}>出生日期</label>
              {needBirthDate ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: '8px' }}>
                  <select value={draftProfile.birth_date ? draftProfile.birth_date.split('-')[0] : ''} onChange={e => {
                    const y = e.target.value
                    const m = draftProfile.birth_date ? draftProfile.birth_date.split('-')[1] : '01'
                    const d = draftProfile.birth_date ? draftProfile.birth_date.split('-')[2] : '01'
                    setDraftProfile({ ...draftProfile, birth_date: `${y}-${m}-${d}` })
                  }} style={dateSelectStyle}>
                    <option value="">年</option>
                    {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                  </select>
                  <select value={draftProfile.birth_date ? draftProfile.birth_date.split('-')[1] : ''} onChange={e => {
                    const y = draftProfile.birth_date ? draftProfile.birth_date.split('-')[0] : currentYear
                    const m = e.target.value
                    const d = draftProfile.birth_date ? draftProfile.birth_date.split('-')[2] : '01'
                    setDraftProfile({ ...draftProfile, birth_date: `${y}-${m}-${d}` })
                  }} style={dateSelectStyle}>
                    <option value="">月</option>
                    {monthOptions.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <select value={draftProfile.birth_date ? draftProfile.birth_date.split('-')[2] : ''} onChange={e => {
                    const y = draftProfile.birth_date ? draftProfile.birth_date.split('-')[0] : currentYear
                    const m = draftProfile.birth_date ? draftProfile.birth_date.split('-')[1] : '01'
                    const d = e.target.value
                    setDraftProfile({ ...draftProfile, birth_date: `${y}-${m}-${d}` })
                  }} style={dateSelectStyle}>
                    <option value="">日</option>
                    {getDayOptions().map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
              ) : (<div style={{ fontSize: '14px', color: '#333', marginBottom: '8px' }}>{profile.birth_date}</div>)}

              <label style={{ fontSize: '13px', color: '#666' }}>出生时间</label>
              {needBirthTime ? (
                <select value={draftProfile.birth_time} onChange={e => setDraftProfile({ ...draftProfile, birth_time: e.target.value })} style={inputStyle}>
                  {timeOptions.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              ) : (<div style={{ fontSize: '14px', color: '#333', marginBottom: '8px' }}>{timeOptions.find(t => t.value === profile.birth_time)?.label || profile.birth_time}</div>)}

              <label style={{ fontSize: '13px', color: '#666' }}>出生地</label>
              {needBirthPlace ? (
                <input type="text" value={draftProfile.birth_place} onChange={e => setDraftProfile({ ...draftProfile, birth_place: e.target.value })} placeholder="例如：浙江省绍兴市" style={inputStyle} />
              ) : (<div style={{ fontSize: '14px', color: '#333', marginBottom: '8px' }}>{profile.birth_place}</div>)}

              <label style={{ fontSize: '13px', color: '#666' }}>现居住地（可修改）</label>
              <input type="text" value={draftProfile.location} onChange={e => setDraftProfile({ ...draftProfile, location: e.target.value })} placeholder="例如：广东省广州市" style={inputStyle} />
            </div>
          ) : (
            <div style={{ fontSize: '14px', color: '#333', lineHeight: '2' }}>
              <div>性别：{profile.gender || '未填写'}</div>
              <div>出生日期：{profile.birth_date || '未填写'}</div>
              <div>出生时间：{profile.birth_time ? (timeOptions.find(t => t.value === profile.birth_time)?.label || profile.birth_time) : '未填写'}</div>
              <div>出生地：{profile.birth_place || '未填写'}</div>
              <div>现居住地：{profile.location || '未填写'}</div>
            </div>
          )}
        </div>
      )}

      <div style={boxStyle}>
        <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>🧑‍⚕️ 角色切换</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
          {['李老师', '李老师智能体', '学生', '学生智能体'].map((role) => (
            <button key={role} style={roleBtnStyle(role)} onClick={() => setCurrentRole(role)}>{role}</button>
          ))}
        </div>
      </div>

      {points && (
        <div style={{ ...boxStyle, display: 'flex', justifyContent: 'space-around', textAlign: 'center', background: '#fffdf5' }}>
          <div>
            <div style={{ fontSize: '12px', color: '#999' }}>{selectedPatient} 积分</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#8b4513' }}>{points.patient_points}</div>
          </div>
          <div>
            <div style={{ fontSize: '12px', color: '#999' }}>{selectedTeacher} 积分</div>
            <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#5a7d5a' }}>{points.teacher_points}</div>
          </div>
        </div>
      )}

      <div style={{ ...boxStyle, background: currentRole.includes('老师') ? '#e8f0e8' : '#fdfcf0' }}>
        <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>{roleData ? `📋 ${roleData.name} 的任务` : '加载中...'}</div>
        <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>{roleData ? roleData.detail : '正在获取数据...'}</div>
        {currentRole === '学生' && roleData?.detail.includes('请记得') && (
          <div style={{ textAlign: 'center', marginTop: '20px' }}><button onClick={handleCheckIn} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>立即打卡（+10积分）</button></div>
        )}
        {currentRole === '李老师' && roleData?.task === '待审核' && roleData?.detail.includes('已打卡') && (
          <div style={{ textAlign: 'center', marginTop: '20px' }}><button onClick={handleApprove} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#5a7d5a', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>签字确认</button></div>
        )}
      </div>

      {(currentRole === '李老师' || currentRole === '李老师智能体') && (
        <div style={{ ...boxStyle, background: '#fff9f0' }}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '5px' }} onClick={() => setShowHistory(!showHistory)}>
            📂 {selectedPatient} 的历史病历 {showHistory ? '▲' : '▼'}
          </div>
          {showHistory && (
            <div style={{ marginTop: '15px' }}>
              {patientRecords.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999' }}>暂无历史病历记录</div>
              ) : (
                patientRecords.map(r => (
                  <div key={r.id} style={{ padding: '12px', border: '1px dashed #d4c8a8', borderRadius: '8px', marginBottom: '15px', background: '#fdfcf0' }}>
                    <div style={{ color: '#5a7d5a', fontSize: '12px', marginBottom: '8px', fontWeight: 'bold' }}>✅ 由 {r.doctor} 签字确认</div>
                    <div style={{ fontSize: '13px', color: '#999', marginBottom: '3px' }}>【智能体原始草案】</div>
                    <div style={{ whiteSpace: 'pre-wrap', fontSize: '13px', color: '#666', background: '#f5f5f5', padding: '8px', borderRadius: '6px', marginBottom: '8px' }}>{r.ai_draft}</div>
                    {/* 【第33天新增】过往病历里的图片 */}
                    {extractImageUrls(r.ai_draft).length > 0 && (
                      <div style={{ marginBottom: '8px', padding: '8px', background: '#fff', borderRadius: '6px', border: '1px dashed #b8d8c0' }}>
                        <div style={{ fontSize: '12px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '6px' }}>📷 学生上传的图片：</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                          {extractImageUrls(r.ai_draft).map((url, i) => (
                            <img key={i} src={url} alt={`学生图片${i + 1}`} style={{ maxWidth: '120px', maxHeight: '120px', objectFit: 'cover', borderRadius: '6px', margin: '3px', border: '1px solid #b8d8c0' }} />
                          ))}
                        </div>
                      </div>
                    )}
                    <div style={{ fontSize: '13px', color: '#8b4513', marginBottom: '3px' }}>【老师最终决策】</div>
                    <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', color: '#333', background: '#fff8e7', padding: '8px', borderRadius: '6px' }}>{r.final_plan}</div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {(currentRole === '李老师' || currentRole === '李老师智能体') && profile && (
        <div style={{ ...boxStyle, background: '#fffaf0' }}>
          <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>📋 {selectedPatient} 的基础档案（供辨证参考）</div>
          <div style={{ fontSize: '14px', color: '#333', lineHeight: '2' }}>
            <div>性别：{profile.gender || '未填写'}</div>
            <div>出生日期：{profile.birth_date || '未填写'}</div>
            <div>出生时间：{profile.birth_time ? (timeOptions.find(t => t.value === profile.birth_time)?.label || profile.birth_time) : '未填写（时辰未知，按子时推算）'}</div>
            <div>出生地：{profile.birth_place || '未填写'}</div>
            <div>现居住地：{profile.location || '未填写'}</div>
            <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontWeight: 'bold' }}>
              八字：{profile.bazi || '缺少出生日期，无法推算'}
            </div>
            {profile.wuxing && (
              <div style={{ color: '#5a7d5a', fontWeight: 'bold' }}>五行体质参考：{profile.wuxing}</div>
            )}
          </div>
        </div>
      )}

      {/* 【第32天】学生端：输入 + 图片草稿 + 结构化预览 + 确认发送 */}
      {(currentRole === '学生' || currentRole === '学生智能体') && (
        <div style={boxStyle}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '15px' }}>🗣️ 学生智能体（先结构化，再发送）</div>
          <textarea
            value={inputText}
            placeholder="在此输入您的感受、症状，或点下方🎤录音..."
            style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '10px', boxSizing: 'border-box' }}
          />
          {/* 【第39天新增】语音录入按钮 */}
          <div style={{ marginBottom: '15px', textAlign: 'center' }}>
            <button
              onClick={startStudentRecording}
              style={{
                padding: '8px 24px',
                borderRadius: '30px',
                border: 'none',
                background: isRecordingStudent ? '#c0392b' : '#8b4513',
                color: '#fff',
                cursor: 'pointer',
                fontSize: '14px',
                fontFamily: 'serif',
              }}
            >
              {isRecordingStudent ? '⏹ 停止录音（点击结束）' : '🎤 开始录音'}
            </button>
            {isRecordingStudent && (
              <div style={{ fontSize: '12px', color: '#c0392b', marginTop: '5px' }}>
                ● 正在录音，请说话...（说完再点一次停止）
              </div>
            )}
          </div>

          {/* 待发送的图片（带删除按钮） */}
          {pendingImages.length > 0 && (
            <div style={{ marginBottom: '15px', padding: '10px', border: '1px dashed #b8d8c0', borderRadius: '8px', background: '#f7fcf9' }}>
              <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📎 待发送的图片（{pendingImages.length}张）</div>
              <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                {pendingImages.map((url, i) => (
                  <div key={i} style={{ position: 'relative', margin: '4px' }}>
                    <img src={url} alt={`待发送${i + 1}`} style={{ width: '100px', height: '100px', objectFit: 'cover', borderRadius: '8px', border: '1px solid #b8d8c0' }} />
                    <button
                      onClick={() => handleRemovePendingImage(url)}
                      style={{ position: 'absolute', top: '2px', right: '2px', width: '22px', height: '22px', borderRadius: '50%', border: 'none', background: '#c0392b', color: '#fff', cursor: 'pointer', fontSize: '12px', lineHeight: '22px', padding: 0 }}
                      title="删除这张"
                    >✕</button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 【第40天新增】待发送的录音 */}
          {pendingAudios.length > 0 && (
            <div style={{ marginBottom: '15px', padding: '10px', border: '1px dashed #b8d8c0', borderRadius: '8px', background: '#f7fcf9' }}>
              <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>🎙️ 待发送的录音（{pendingAudios.length}段）</div>
              {pendingAudios.map((url, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', marginBottom: '5px' }}>
                  <audio src={url} controls style={{ flex: 1, height: '30px' }} />
                  <button
                    onClick={() => setPendingAudios(prev => prev.filter(u => u !== url))}
                    style={{ marginLeft: '8px', padding: '2px 8px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}
                  >删除</button>
                </div>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', marginBottom: '15px' }}>
            <button onClick={handleTranscribe} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>整理成结构化陈述</button>
            <button onClick={() => fileInputRef.current?.click()} style={{ padding: '10px 24px', borderRadius: '30px', border: '1px solid #8b4513', background: '#fdfcf0', color: '#8b4513', fontSize: '16px', cursor: 'pointer' }} disabled={uploading}>
              {uploading ? '上传中...' : '📷 添加图片'}
            </button>
            <input type="file" ref={fileInputRef} onChange={handleImageUpload} accept="image/*" style={{ display: 'none' }} />
          </div>

          {structuredPreview && (
            <div style={{ marginTop: '15px', borderTop: '1px dashed #d4c8a8', paddingTop: '15px' }}>
              <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📋 请确认以下内容后发送：</div>
              <textarea
                value={structuredPreview}
                onChange={(e) => setStructuredPreview(e.target.value)}
                style={{ width: '100%', height: '150px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#f7fcf9', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box' }}
              />
              {/* 结构化预览里的图片缩略图（确认用） */}
              {pendingImages.length > 0 && (
                <div style={{ marginBottom: '10px' }}>
                  <div style={{ fontSize: '12px', color: '#666', marginBottom: '5px' }}>将一并发送以下图片：</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                    {pendingImages.map((url, i) => (
                      <img key={i} src={url} alt={`待发送${i + 1}`} style={{ width: '80px', height: '80px', objectFit: 'cover', borderRadius: '6px', margin: '3px', border: '1px solid #b8d8c0' }} />
                    ))}
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button onClick={() => setStructuredPreview(null)} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontSize: '13px' }}>取消</button>
                <button onClick={handleConfirmSend} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>确认发送给 {selectedTeacher}</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 老师端：病历草案（老师智能体按老师模板生成） */}
      {(currentRole === '李老师' || currentRole === '李老师智能体') && (
        <div style={{ ...boxStyle, background: '#fcfdfa' }}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '15px' }}>📄 病历草案（老师智能体生成，待老师补充）</div>
          {drafts.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#999' }}>暂无待处理病历</div>
          ) : (
            drafts.map(d => (
              <div key={d.id} style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '8px', marginBottom: '15px', background: '#fff' }}>
                <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '5px' }}>学生：{d.patient_name}</div>
                <textarea value={d.content} onChange={(e) => { const newDrafts = drafts.map(item => item.id === d.id ? { ...item, content: e.target.value } : item); setDrafts(newDrafts); }} style={{ width: '100%', height: '180px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box', whiteSpace: 'pre-wrap' }} />

                {/* 病历里自动显示图片 */}
                {extractImageUrls(d.content).length > 0 && (
                  <div style={{ marginBottom: '15px', padding: '10px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
                    <div style={{ fontSize: '12px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📷 学生上传的图片：</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                      {extractImageUrls(d.content).map((url, i) => (
                        <img key={i} src={url} alt={`学生图片${i + 1}`} style={{ maxWidth: '150px', maxHeight: '150px', objectFit: 'cover', borderRadius: '8px', margin: '4px', border: '1px solid #b8d8c0' }} />
                      ))}
                    </div>
                  </div>
                )}

                {/* 病历里自动显示音频 */}
                {extractAudioUrls(d.content).length > 0 && (
                  <div style={{ marginBottom: '15px', padding: '10px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
                    <div style={{ fontSize: '12px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>🎙️ 学生录音：</div>
                    {extractAudioUrls(d.content).map((url, i) => (
                      <audio key={i} src={url} controls style={{ width: '100%', marginBottom: '5px' }} />
                    ))}
                  </div>
                )}

                {/* 现场辅助记录 - 大段录音 + AI整理 */}
                <div style={{ marginTop: '15px', padding: '12px', background: '#f0f7f0', borderRadius: '8px', border: '1px dashed #5a7d5a' }}>
                  <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>📸 现场辅助记录（老师口述 → AI整理）</div>

                  <textarea
                    placeholder="点击下方 🎤 录音，口述望闻问切内容；或直接打字..."
                    value={teacherLiveText[d.id] || ''}
                    onChange={e => setTeacherLiveText(prev => ({ ...prev, [d.id]: e.target.value }))}
                    style={{ width: '100%', minHeight: '100px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#fff', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box' }}
                  />

                  <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                    <button
                      onClick={() => startTeacherLiveRecording(d.id)}
                      style={{ flex: 1, padding: '8px', borderRadius: '20px', border: 'none', background: teacherLiveRecording === d.id ? '#c0392b' : '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '13px' }}
                    >
                      {teacherLiveRecording === d.id ? '⏹ 停止录音' : '🎤 开始录音'}
                    </button>
                    <button
                      onClick={() => handleTeacherStructurize(d.id)}
                      disabled={teacherLiveStructurizing[d.id]}
                      style={{ flex: 1, padding: '8px', borderRadius: '20px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '13px' }}
                    >
                      {teacherLiveStructurizing[d.id] ? 'AI整理中...' : '🤖 AI整理成病历格式'}
                    </button>
                    <label style={{ flex: 1, padding: '8px', borderRadius: '20px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '13px', textAlign: 'center' }}>
                      {liveUploading[d.id] ? '上传中...' : '📷 拍照'}
                      <input type="file" accept="image/*" capture="environment" onChange={(e) => handleLivePhotoUpload(d.id, e)} style={{ display: 'none' }} />
                    </label>
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button onClick={() => handleAppendTeacherNote(d.id)} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>追加到病历</button>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '15px' }}>
                  <button onClick={() => handleEditDraft(d.id, d.content)} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer' }}>保存病历修改</button>
                </div>

                <div style={{ borderTop: '1px dashed #d4c8a8', paddingTop: '15px' }}>
                  <div style={{ color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📝 给 {d.patient_name} 的辨证施治方案（学生会看到这里的内容）</div>
                  <textarea value={finalPlans[d.id] || ''} onChange={(e) => setFinalPlans({ ...finalPlans, [d.id]: e.target.value })} placeholder="例：抓药xxx，三碗水煲成一碗，饭后服；或今日宜喝姜茶，多休息..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#f7fcf9', fontFamily: 'serif', fontSize: '14px', marginBottom: '10px', boxSizing: 'border-box' }} />
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button onClick={() => handleSignDraft(d.id)} style={{ padding: '8px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontWeight: 'bold' }}>签字并回复学生</button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* 学生端：老师的回应 */}
      {(currentRole === '学生' || currentRole === '学生智能体') && (
        <div style={{ ...boxStyle, background: '#f7fcf9' }}>
          <div style={{ textAlign: 'center', fontSize: '18px', color: '#5a7d5a', marginBottom: '15px' }}>💬 {selectedTeacher}的回应</div>
          <div style={{ textAlign: 'center', fontSize: '13px', color: '#999', fontStyle: 'italic', lineHeight: '1.8', marginBottom: '15px' }}>
            您的病历数据归您所有，由老师签字确认。<br />
            如有疑问，请在下一次问诊时向老师咨询。
          </div>
          {patientRecords.length > 0 ? (
            <div style={{ padding: '15px', border: '1px solid #b8d8c0', borderRadius: '8px', background: '#fff' }}>
              <div style={{ color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📌 最近一次回复</div>
              <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', color: '#333', lineHeight: '1.6' }}>{patientRecords[0].final_plan}</div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', color: '#999', padding: '20px' }}>暂无回复，等待老师签字确认。</div>
          )}
        </div>
      )}

    </div>
  </div>
)
}