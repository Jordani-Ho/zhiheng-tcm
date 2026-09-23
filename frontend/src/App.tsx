import { useEffect, useState, useRef } from 'react'

interface HuangliData { date: string; lunar: string; solar_term: string; solar_term_tip: string; health_trend: string; homework: string; }
interface RoleData { role_type: string; name: string; task: string; detail: string; }
interface Draft { id: number; transcript_id: number; patient_name: string; content: string; signed: boolean; doctor?: string; }
interface Patient { name: string; teacher_name: string; guardian_name: string; relation: string; }
interface PatientRecord { id: number; patient_name: string; ai_draft: string; final_plan: string; doctor: string; }
interface PatientProfile { patient_name: string; gender: string; birth_date: string; birth_time: string; birth_place: string; location: string; bazi?: string; wuxing?: string; }
interface Teacher { name: string; description: string; }

const boxStyle: React.CSSProperties = { background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '24px', marginBottom: '20px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }
const inputStyle: React.CSSProperties = { width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '8px', boxSizing: 'border-box' }
const dateSelectStyle: React.CSSProperties = { padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginRight: '6px', marginBottom: '8px' }

export default function App() {
  const now = new Date()
  const currentYear = now.getFullYear()
  const currentMonth = now.getMonth() + 1
  const currentDay = now.getDate()

  const [huangli, setHuangli] = useState<HuangliData | null>(null)
  const [currentRole, setCurrentRole] = useState('学生')
  const [roleData, setRoleData] = useState<RoleData | null>(null)
  const [inputText, setInputText] = useState('')
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [patientRecords, setPatientRecords] = useState<PatientRecord[]>([])
  const [finalPlans, setFinalPlans] = useState<{ [key: number]: string }>({})
  const [points, setPoints] = useState<{ patient_points: number; teacher_points: number } | null>(null)
  const [patients, setPatients] = useState<Patient[]>([])
  const [selectedPatient, setSelectedPatient] = useState('张三')
  const [showHistory, setShowHistory] = useState(false)
  const [profile, setProfile] = useState<PatientProfile | null>(null)
  const [editingProfile, setEditingProfile] = useState(false)
  const [draftProfile, setDraftProfile] = useState<PatientProfile | null>(null)

  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [patientTeachers, setPatientTeachers] = useState<string[]>([])
  const [selectedTeacher, setSelectedTeacher] = useState('李老师')
  const [showTeacherPicker, setShowTeacherPicker] = useState(false)
  const [teacherPatients, setTeacherPatients] = useState<any[]>([])

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

  const [healthTrend, setHealthTrend] = useState<any>(null)
  const [dailyAdvice, setDailyAdvice] = useState<any>(null)

  const [invites, setInvites] = useState<any[]>([])
  const [pendingInviteCode, setPendingInviteCode] = useState<string>('')
  const [newStudentNameFromInvite, setNewStudentNameFromInvite] = useState<string>('')

  const [structuredPreview, setStructuredPreview] = useState<string | null>(null)
  const [pendingImages, setPendingImages] = useState<string[]>([])
  const [pendingAudios, setPendingAudios] = useState<string[]>([])
  const [isRecordingStudent, setIsRecordingStudent] = useState(false)
  const [recognitionStudent, setRecognitionStudent] = useState<any>(null)
  const [mediaRecorder, setMediaRecorder] = useState<any>(null)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [teacherLiveText, setTeacherLiveText] = useState<{ [draftId: number]: string }>({})
  const [teacherLiveRecording, setTeacherLiveRecording] = useState<number | null>(null)
  const [teacherLiveRecognition, setTeacherLiveRecognition] = useState<any>(null)
  const [teacherLiveStructurizing, setTeacherLiveStructurizing] = useState<{ [draftId: number]: boolean }>({})
  const [liveUploading, setLiveUploading] = useState<{ [draftId: number]: boolean }>({})

  const [previewDraft, setPreviewDraft] = useState<{ id: number; content: string } | null>(null)
  const [draftTags, setDraftTags] = useState<{ [draftId: number]: { area: string; symptom: string } }>({})

  // 预约相关
  const [appointments, setAppointments] = useState<any[]>([])
  const [showApptForm, setShowApptForm] = useState(false)
  const [apptDate, setApptDate] = useState('')
  const [apptTime, setApptTime] = useState('')
  const [apptReason, setApptReason] = useState('')

  // 老师工作时间（新）
  const [schedule, setSchedule] = useState<{ [day: string]: string[] } | null>(null)
  const [scheduleEditDay, setScheduleEditDay] = useState('1') // 当前编辑的星期，默认周一
  const [editingSchedule, setEditingSchedule] = useState(false)
  const [tempSchedule, setTempSchedule] = useState<{ [day: string]: string[] }>({})
  // 【第49天新增】节假日管理
  const [holidays, setHolidays] = useState<string[]>([])
  const [newHolidayDate, setNewHolidayDate] = useState('')
    // 【第51天新增】中药材库存
  const [herbs, setHerbs] = useState<any[]>([])
  const [showHerbForm, setShowHerbForm] = useState(false)
  // 【第55天新增】库存量/预警阈值改为默认留空（保存时留空分别按 0 / 50 处理），用户不必先删 0
  const [herbForm, setHerbForm] = useState({ herb_name: '', stock_amount: '', unit: '克', warn_threshold: '' })
  const [showLowOnly, setShowLowOnly] = useState(false)
  const [adjustingHerb, setAdjustingHerb] = useState<any>(null)
  const [adjustDelta, setAdjustDelta] = useState(0)
  // 【第52天新增】开方（中药材首字联想 + 药方结构化存储）
  const [prescriptionPatient, setPrescriptionPatient] = useState('')
  // 【第54天新增】amount 改为 string：默认留空，用户不必先删 0（保存时按 0 处理）
  const [prescriptionItems, setPrescriptionItems] = useState<{ herb_name: string; amount: string }[]>([{ herb_name: '', amount: '' }])
  const [herbSuggestions, setHerbSuggestions] = useState<{ [index: number]: any[] }>({})
  const herbSearchTimers = useRef<{ [index: number]: any }>({})
  const [savingPrescription, setSavingPrescription] = useState(false)
  // 【第53天新增】远程诊疗（勾选则不扣库存；默认当面诊疗，扣库存）
  const [prescriptionRemote, setPrescriptionRemote] = useState(false)
  // 【第56天新增】智能体工作台（沉默学生请示闭环）
  const [agentTasks, setAgentTasks] = useState<any[]>([])
  const [scanningAgent, setScanningAgent] = useState(false)
    // 【第50天新增】可视化排班网格
  const [calendarData, setCalendarData] = useState<any>(null)
  const [selectedDayIndex, setSelectedDayIndex] = useState(0)
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

  const extractImageUrls = (content: string): string[] => {
    const regex = /\/uploads\/[a-zA-Z0-9._-]+\.(?:jpg|jpeg|png|gif|webp)/g
    const matches = content.match(regex)
    return matches ? Array.from(new Set(matches)) : []
  }
  const extractAudioUrls = (content: string): string[] => {
    const regex = /\/uploads\/audio_[a-zA-Z0-9._-]+/g
    const matches = content.match(regex)
    return matches ? Array.from(new Set(matches)) : []
  }

  // ============== 初始化 ==============
  useEffect(() => {
    fetch('/api/huangli').then(r => r.json()).then(d => setHuangli(d)).catch(() => setHuangli(null))
    fetch('/api/teachers').then(r => r.json()).then(d => setTeachers(d)).catch(() => setTeachers([]))
    fetchPatients('张三')
    const urlParams = new URLSearchParams(window.location.search)
    const inviteCode = urlParams.get('invite')
    if (inviteCode) setPendingInviteCode(inviteCode)
    fetch('/api/patient-profile?patient_name=张三')
      .then(r => r.json())
      .then(d => {
        setGuardianLocation(d.location || '')
        setGuardianGender(d.gender || '')
        setGuardianBirthDate(d.birth_date || '')
      })
      .catch(() => {})
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
        .then(r => r.json()).then(d => setTeacherPatients(d))
        .catch(() => setTeacherPatients([]))
      fetchSchedule()
      fetchHolidays()
      fetchCalendar()
      fetchHerbs()
    }
  }, [currentRole, selectedTeacher])

  // 【第56天新增】智能体工作台：进入老师端时拉取待办请示
  useEffect(() => {
    if (currentRole === '李老师' || currentRole === '李老师智能体') {
      fetchAgentTasks()
    }
  }, [currentRole, selectedTeacher])

  useEffect(() => {
    fetchRoleData()
    fetchDrafts()
    fetchPatientRecords()
    fetchPoints()
    fetchProfile()
    fetchHealthTrend()
    fetchDailyAdvice()
    fetchAppointments()
    fetchCalendar()
    setShowHistory(false)
  }, [currentRole, selectedPatient, selectedTeacher])

  // ============== 数据获取 ==============
  const fetchPatients = (guardian: string) => {
    fetch(`/api/patients?guardian_name=${guardian}`).then(r => r.json()).then(d => setPatients(d)).catch(() => setPatients([]))
  }
  const fetchRoleData = () => {
    fetch(`/api/role-data?role=${currentRole}&patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => setRoleData(d)).catch(() => setRoleData(null))
  }
  const fetchDrafts = () => {
    fetch(`/api/drafts?teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => setDrafts(d)).catch(() => setDrafts([]))
  }
  const fetchPatientRecords = () => {
    fetch(`/api/patient-records?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => {
        const sorted = [...d].sort((a: any, b: any) => b.id - a.id)
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
    fetch(`/api/health-trend?patient_name=${selectedPatient}`)
      .then(r => r.json()).then(d => setHealthTrend(d && !d.error ? d : null))
      .catch(() => setHealthTrend(null))
  }
  const fetchDailyAdvice = () => {
    fetch(`/api/daily-advice?patient_name=${selectedPatient}`)
      .then(r => r.json()).then(d => setDailyAdvice(d && !d.error ? d : null))
      .catch(() => setDailyAdvice(null))
  }
  const fetchInvites = () => {
    fetch(`/api/invites?teacher_name=${selectedTeacher}`).then(r => r.json()).then(d => setInvites(d)).catch(() => setInvites([]))
  }

  // 老师工作时间
  const fetchSchedule = () => {
    fetch(`/api/teacher-schedule?teacher_name=${selectedTeacher}`)
      .then(r => r.json())
      .then(d => {
        setSchedule(d)
        setTempSchedule(JSON.parse(JSON.stringify(d)))
      })
      .catch(() => setSchedule(null))
  }

  const handleSaveSchedule = () => {
    fetch('/api/teacher-schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher, schedule: tempSchedule })
    }).then(() => {
      setSchedule(JSON.parse(JSON.stringify(tempSchedule)))
      setEditingSchedule(false)
      alert("工作时间已保存")
    })
  }

    // 【第49天新增】节假日
  const fetchHolidays = () => {
    fetch(`/api/teacher-holidays?teacher_name=${selectedTeacher}`)
      .then(r => r.json())
      .then(d => setHolidays(Array.isArray(d) ? d : []))
      .catch(() => setHolidays([]))
  }

  const handleAddHoliday = () => {
    if (!newHolidayDate) { alert("请选择日期"); return }
    if (holidays.includes(newHolidayDate)) { alert("该日期已在节假日列表"); return }
    const updated = [...holidays, newHolidayDate].sort()
    fetch('/api/teacher-holidays', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher, holidays: updated })
    }).then(() => { setHolidays(updated); setNewHolidayDate('') })
  }

  const handleRemoveHoliday = (date: string) => {
    if (!confirm(`确定要移除【${date}】吗？`)) return
    const updated = holidays.filter(d => d !== date)
    fetch('/api/teacher-holidays', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher, holidays: updated })
    }).then(() => setHolidays(updated))
  }

  
  // 【第51天新增】中药材库存
  const fetchHerbs = () => {
    fetch(`/api/herbs?teacher_name=${encodeURIComponent(selectedTeacher)}`)
      .then(res => res.json())
      .then(data => setHerbs(data))
  }

  const toggleLowOnly = () => {
    const next = !showLowOnly
    setShowLowOnly(next)
    const url = next
      ? `/api/herbs/low?teacher_name=${encodeURIComponent(selectedTeacher)}`
      : `/api/herbs?teacher_name=${encodeURIComponent(selectedTeacher)}`
    fetch(url).then(res => res.json()).then(data => setHerbs(data))
  }

  const handleSaveHerb = () => {
    // 【第55天新增】两个数字框留空时按默认值处理：库存量 0、预警阈值 50（显式填 0 则按 0）
    const numOr = (value: string, fallback: number) => {
      const trimmed = value.trim()
      if (trimmed === '') return fallback
      const parsed = parseFloat(trimmed)
      return Number.isNaN(parsed) ? fallback : parsed
    }
    const stockAmount = numOr(herbForm.stock_amount, 0)
    const warnThreshold = numOr(herbForm.warn_threshold, 50)
    fetch('/api/herbs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        teacher_name: selectedTeacher,
        herb_name: herbForm.herb_name,
        stock_amount: stockAmount,
        unit: herbForm.unit,
        warn_threshold: warnThreshold
      })
    })
      .then(res => res.json())
      .then(() => {
        setShowHerbForm(false)
        setHerbForm({ herb_name: '', stock_amount: '', unit: '克', warn_threshold: '' })
        fetchHerbs()
      })
  }

  const openAdjustModal = (herb: any) => {
    setAdjustingHerb(herb)
    setAdjustDelta(0)
  }

  const submitAdjust = () => {
    if (!adjustingHerb) return
    fetch(`/api/herbs/${adjustingHerb.id}/adjust`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta: adjustDelta })
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(err => { throw new Error(err.detail || '调整失败') })
        }
        return res.json()
      })
      .then(() => {
        setAdjustingHerb(null)
        setAdjustDelta(0)
        fetchHerbs()
      })
      .catch(err => alert(err.message))
  }

  const handleDeleteHerb = (herbId: number) => {
    if (!window.confirm('确定删除该药材记录吗？')) return
    fetch(`/api/herbs/${herbId}`, { method: 'DELETE' })
      .then(res => res.json())
      .then(() => fetchHerbs())
  }

  // 【第52天新增】开方：药材名首字联想（debounce 300ms）
  const searchHerbSuggestions = (index: number, prefix: string) => {
    if (herbSearchTimers.current[index]) clearTimeout(herbSearchTimers.current[index])
    const keyword = prefix.trim()
    if (!keyword) {
      setHerbSuggestions(prev => ({ ...prev, [index]: [] }))
      return
    }
    herbSearchTimers.current[index] = setTimeout(() => {
      fetch(`/api/herbs/search?teacher_name=${encodeURIComponent(selectedTeacher)}&prefix=${encodeURIComponent(keyword)}`)
        .then(res => res.json())
        .then(data => setHerbSuggestions(prev => ({ ...prev, [index]: data })))
        .catch(() => setHerbSuggestions(prev => ({ ...prev, [index]: [] })))
    }, 300)
  }

  const changePrescriptionItem = (index: number, field: 'herb_name' | 'amount', value: string) => {
    setPrescriptionItems(prev => prev.map((item, i) => {
      if (i !== index) return item
      // 【第54天新增】数量按原始字符串存，允许空值
      return field === 'amount' ? { ...item, amount: value } : { ...item, herb_name: value }
    }))
    if (field === 'herb_name') searchHerbSuggestions(index, value)
  }

  const pickHerbSuggestion = (index: number, herb: any) => {
    setPrescriptionItems(prev => prev.map((item, i) => (i === index ? { ...item, herb_name: herb.herb_name } : item)))
    setHerbSuggestions(prev => ({ ...prev, [index]: [] }))
  }

  const addPrescriptionItem = () => {
    setPrescriptionItems(prev => [...prev, { herb_name: '', amount: '' }])
  }

  const handleSavePrescription = () => {
    const items = prescriptionItems
      .filter(item => item.herb_name.trim())
      // 【第54天新增】留空视为 0 克
      .map(item => ({ herb_name: item.herb_name.trim(), amount: parseFloat(item.amount) || 0, unit: '克' }))
    if (items.length === 0) { alert('请至少填写一味药材'); return }
    setSavingPrescription(true)
    fetch('/api/prescriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 一期没有备注输入框，note 先传空串（后端/表结构已支持）
      body: JSON.stringify({ teacher_name: selectedTeacher, patient_name: prescriptionPatient, items, note: '', is_remote: prescriptionRemote })
    })
      .then(res => res.json())
      .then(data => {
        setSavingPrescription(false)
        // 当面诊疗扣库存失败 → 弹窗提示，不保存（表单保留，方便老师改数量）
        if (data.error) { alert(data.error); return }
        setPrescriptionPatient('')
        setPrescriptionItems([{ herb_name: '', amount: '' }])
        setHerbSuggestions({})
        setPrescriptionRemote(false)
        if (prescriptionRemote) {
          alert('药方已保存（远程诊疗，库存未变）')
        } else {
          fetchHerbs()
          alert('药方已保存，库存已扣减')
        }
      })
      .catch(() => { setSavingPrescription(false); alert('保存失败，请重试') })
  }

  // 【第56天新增】智能体工作台：拉取待办 / 触发扫描 / 处理请示（确认执行或忽略）
  const fetchAgentTasks = () => {
    fetch(`/api/agent/tasks?teacher_name=${encodeURIComponent(selectedTeacher)}&status=pending`)
      .then(res => res.json())
      .then(data => setAgentTasks(data))
      .catch(() => setAgentTasks([]))
  }

  const handleAgentScan = () => {
    setScanningAgent(true)
    fetch(`/api/agent/scan?teacher_name=${encodeURIComponent(selectedTeacher)}`, { method: 'POST' })
      .then(res => res.json())
      .then(data => {
        setScanningAgent(false)
        fetchAgentTasks()
        alert(data.new_tasks > 0 ? `智能体发现 ${data.new_tasks} 条新请示` : '没有发现新的待办')
      })
      .catch(() => { setScanningAgent(false); alert('扫描失败，请重试') })
  }

  const handleResolveAgentTask = (taskId: number, decision: 'approved' | 'rejected') => {
    fetch(`/api/agent/tasks/${taskId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision })
    })
      .then(res => res.json())
      .then(() => fetchAgentTasks())
      .catch(() => alert('处理失败，请重试'))
  }
    // 【第50天新增】拉取可视化排班数据
  const fetchCalendar = () => {
    fetch(`/api/appointments/calendar?teacher_name=${selectedTeacher}`)
      .then(r => r.json())
      .then(d => setCalendarData(d))
      .catch(() => setCalendarData(null))
  }
  
  // 切换某天某个时段
  const toggleSlot = (day: string, slot: string) => {
    setTempSchedule(prev => {
      const daySlots = prev[day] || []
      const newSlots = daySlots.includes(slot) ? daySlots.filter(s => s !== slot) : [...daySlots, slot].sort()
      return { ...prev, [day]: newSlots }
    })
  }

  // ============== 学生端行为 ==============
  const handleCheckIn = () => {
    fetch(`/api/check-in?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`, { method: 'POST' })
      .then(() => { fetchRoleData(); fetchPoints() })
  }
  const handleApprove = () => {
    fetch(`/api/approve?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`, { method: 'POST' })
      .then(() => fetchRoleData())
  }

  const startStudentRecording = async () => {
    if (isRecordingStudent) {
      mediaRecorder?.stop()
      recognitionStudent?.stop()
      setIsRecordingStudent(false)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const chunks: Blob[] = []
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' })
        const formData = new FormData()
        formData.append('file', blob, 'recording.webm')
        try {
          const r = await fetch('/api/upload-audio', { method: 'POST', body: formData })
          const d = await r.json()
          if (d.url) setPendingAudios(prev => [...prev, d.url])
        } catch (e) { console.error('音频上传失败', e) }
        stream.getTracks().forEach(t => t.stop())
      }
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (SR) {
        const rec = new SR()
        rec.continuous = true
        rec.interimResults = false
        rec.lang = 'zh-CN'
        rec.onresult = (event: any) => {
          let finalTranscript = ''
          for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript
          }
          if (finalTranscript) setInputText(prev => prev + finalTranscript)
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

  const handleTranscribe = () => {
    if (!inputText.trim() && pendingImages.length === 0 && pendingAudios.length === 0) {
      alert("请先输入文字、录音或上传图片"); return
    }
    fetch('/api/patient-structurize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, raw_text: inputText })
    })
      .then(r => r.json())
      .then(d => {
        const notes: string[] = []
        if (pendingImages.length > 0) notes.push(`${pendingImages.length} 张图片`)
        if (pendingAudios.length > 0) notes.push(`${pendingAudios.length} 段录音`)
        const attachText = notes.length > 0 ? `\n\n（本次将随附：${notes.join('、')}）` : ''
        const preview = `【学生自述】\n学生姓名：${selectedPatient}\n就诊时间：${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日\n\n${d.structured}${attachText}\n\n（以上内容已经过学生智能体整理，待学生确认后发送给老师）`
        setStructuredPreview(preview)
      })
      .catch(() => {
        const preview = `【学生自述】\n学生姓名：${selectedPatient}\n就诊时间：${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日\n主诉内容：${inputText}\n\n（以上为学生原话转述，未经智能体推断）`
        setStructuredPreview(preview)
      })
  }

  const handleConfirmSend = async () => {
    if (!structuredPreview) return
    const imagePart = pendingImages.length > 0
      ? '\n\n【学生上传的图片】\n' + pendingImages.map((url, i) => `图片${i+1}：${url}`).join('\n') : ''
    const audioPart = pendingAudios.length > 0
      ? '\n\n【学生上传的录音】\n' + pendingAudios.map((url, i) => `录音${i+1}：${url}`).join('\n') : ''
    const fullContent = structuredPreview + imagePart + audioPart

    await fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, teacher_name: selectedTeacher, content: fullContent, data_type: 'text' })
    })

    setInputText(''); setPendingImages([]); setPendingAudios([]); setStructuredPreview(null)
    fetchDrafts()
  }

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
      .catch(() => { setUploading(false); alert("图片上传失败") })
  }

  const handleRemovePendingImage = (url: string) => {
    setPendingImages(prev => prev.filter(u => u !== url))
  }

  // ============== 老师端行为 ==============
  const startTeacherLiveRecording = (draftId: number) => {
    if (teacherLiveRecording === draftId) {
      teacherLiveRecognition?.stop(); setTeacherLiveRecording(null); return
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) { alert("当前浏览器不支持语音识别。"); return }
    const rec = new SR()
    rec.continuous = true
    rec.interimResults = false
    rec.lang = 'zh-CN'
    rec.onresult = (event: any) => {
      let finalTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript
      }
      if (finalTranscript) setTeacherLiveText(prev => ({ ...prev, [draftId]: (prev[draftId] || '') + finalTranscript }))
    }
    rec.onerror = () => setTeacherLiveRecording(null)
    rec.onend = () => setTeacherLiveRecording(null)
    rec.start()
    setTeacherLiveRecognition(rec)
    setTeacherLiveRecording(draftId)
  }

  const handleTeacherStructurize = (draftId: number) => {
    const raw = teacherLiveText[draftId]
    if (!raw || !raw.trim()) { alert("请先录音或输入内容"); return }
    setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: true }))
    fetch('/api/teacher-structurize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: raw })
    })
      .then(r => r.json())
      .then(d => {
        setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: false }))
        if (d.structured) setTeacherLiveText(prev => ({ ...prev, [draftId]: d.structured }))
      })
      .catch(() => { setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: false })); alert("AI 整理失败") })
  }

  const handleEditDraft = (draftId: number, newContent: string) => {
    fetch(`/api/drafts/${draftId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: newContent })
    }).then(() => fetchDrafts())
  }

  const handleAppendTeacherNote = (draftId: number) => {
    const text = teacherLiveText[draftId]
    if (!text || !text.trim()) { alert("请先录音或输入内容"); return }
    const draft = drafts.find(x => x.id === draftId)
    if (draft) {
      handleEditDraft(draftId, draft.content + '\n\n【现场记录】\n' + text)
      setTeacherLiveText(prev => ({ ...prev, [draftId]: '' }))
    }
  }

  const handleLivePhotoUpload = (draftId: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLiveUploading(prev => ({ ...prev, [draftId]: true }))
    const formData = new FormData()
    formData.append('file', file)
    fetch('/api/upload-temp', { method: 'POST', body: formData })
      .then(r => r.json())
      .then(d => {
        const draft = drafts.find(x => x.id === draftId)
        if (draft) {
          handleEditDraft(draftId, draft.content + `\n\n【现场照片】\n[老师现场拍摄：${d.url}]`)
        }
        setLiveUploading(prev => ({ ...prev, [draftId]: false }))
      })
      .catch(() => { setLiveUploading(prev => ({ ...prev, [draftId]: false })); alert("照片上传失败") })
  }

  const handlePreviewFullRecord = (draftId: number) => {
    const draft = drafts.find(x => x.id === draftId)
    if (!draft) return
    const plan = finalPlans[draftId] || ''
    if (!plan.trim()) { alert("请先填写施治方案，再预览完整病历"); return }
    const fullContent = draft.content + '\n\n【辨证施治方案】\n' + plan + '\n\n【签字】\n' + selectedTeacher + ' · ' + currentYear + '年' + currentMonth + '月' + currentDay + '日'
    setPreviewDraft({ id: draftId, content: fullContent })
  }

  const handleFinalSign = () => {
    if (!previewDraft) return
    const currentPreview = previewDraft
    const tagData = draftTags[currentPreview.id]
    const saveTags = (): Promise<any> => {
      const tags: any[] = []
      if (tagData?.area?.trim()) tags.push({ tag_type: '部位', tag_value: tagData.area.trim() })
      if (tagData?.symptom?.trim()) tags.push({ tag_type: '症状', tag_value: tagData.symptom.trim() })
      if (tags.length === 0) return Promise.resolve()
      return fetch('/api/tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ record_id: currentPreview.id, teacher_name: selectedTeacher, tags })
      })
    }
    saveTags().then(() => {
      return fetch(`/api/drafts/${currentPreview.id}/sign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          final_plan: finalPlans[currentPreview.id] || '',
          final_content: currentPreview.content
        })
      })
    }).then(() => {
      setPreviewDraft(null)
      setDraftTags(prev => ({ ...prev, [currentPreview.id]: { area: '', symptom: '' } }))
      fetchDrafts(); fetchPatientRecords(); fetchPoints()
      setFinalPlans(prev => ({ ...prev, [currentPreview.id]: '' }))
    })
  }

  // ============== 档案 ==============
  const handleSaveProfile = () => {
    if (!draftProfile) return
    fetch('/api/patient-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draftProfile)
    }).then(() => { setEditingProfile(false); fetchProfile() })
  }

  const handleRelationChange = (value: string) => {
    setNewRelation(value)
    if (['父亲', '儿子'].includes(value)) setNewGender('男')
    else if (['母亲', '女儿'].includes(value)) setNewGender('女')
    else if (value === '配偶') {
      if (guardianGender === '男') setNewGender('女')
      else if (guardianGender === '女') setNewGender('男')
      else { setNewGender(''); alert("请先填写您的性别。") }
    } else setNewGender('')
  }

  const handleToggleAddFamily = () => {
    if (!showAddFamily) {
      setNewLocation(guardianLocation)
      setNewBirthPlace(guardianLocation)
    }
    setShowAddFamily(!showAddFamily)
  }

  const handleAddFamily = () => {
    if (patients.length >= 5) { alert("最多只能添加 5 位家庭成员（含本人）。"); return }
    if (!newFamilyName.trim() || !newRelation.trim() || !newGender || !newBirthYear || !newBirthMonth || !newBirthDay) {
      alert("请至少填写姓名、关系、性别和完整的出生年月日！"); return
    }
    if (patients.some(p => p.name === newFamilyName.trim())) { alert(`家属【${newFamilyName.trim()}】已存在。`); return }
    if (['父亲', '母亲'].includes(newRelation) && guardianBirthDate) {
      const mm = String(newBirthMonth).padStart(2, '0')
      const dd = String(newBirthDay).padStart(2, '0')
      const familyDate = `${newBirthYear}-${mm}-${dd}`
      if (familyDate >= guardianBirthDate) { alert(`【${newRelation}】的出生日期应早于您的出生日期。`); return }
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
    if (!confirm(`确定要删除亲友【${name}】吗？`)) return
    fetch(`/api/patients/${name}`, { method: 'DELETE' }).then(() => {
      if (selectedPatient === name) setSelectedPatient('张三')
      fetchPatients('张三')
    })
  }

  // ============== 老师/邀请码 ==============
  const handleAddTeacher = (teacherName: string) => {
    fetch('/api/patient-teachers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, teacher_name: teacherName })
    }).then(r => r.json()).then(d => {
      if (d.error) { alert(d.error); return }
      fetch(`/api/patient-teachers?patient_name=${selectedPatient}`).then(r => r.json()).then((list: string[]) => setPatientTeachers(list))
    })
  }

  const handleRemoveTeacher = (teacherName: string) => {
    if (!confirm(`确定要退出老师【${teacherName}】的咨询吗？`)) return
    fetch(`/api/patient-teachers?patient_name=${selectedPatient}&teacher_name=${teacherName}`, { method: 'DELETE' })
      .then(() => {
        fetch(`/api/patient-teachers?patient_name=${selectedPatient}`).then(r => r.json()).then((list: string[]) => {
          setPatientTeachers(list)
          if (selectedTeacher === teacherName && list.length > 0) setSelectedTeacher(list[0])
        })
      })
  }

  const handleCreateInvite = () => {
    fetch('/api/invites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher })
    }).then(r => r.json()).then(d => {
      if (d.code) { fetchInvites(); alert(`邀请码已生成：${d.code}`) }
    })
  }

  const handleCopyInviteLink = (code: string) => {
    const link = `${window.location.origin}/?invite=${code}`
    navigator.clipboard.writeText(link).then(() => alert(`已复制：\n${link}`)).catch(() => alert(`请手动复制：\n${link}`))
  }

  const handleAcceptInvite = () => {
    if (!newStudentNameFromInvite.trim()) { alert("请输入您的姓名"); return }
    fetch('/api/invites/accept', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: pendingInviteCode, student_name: newStudentNameFromInvite.trim() })
    }).then(r => r.json()).then(d => {
      if (d.error) { alert(d.error); return }
      alert(`欢迎加入！您已加入 ${d.teacher_name} 的学习小组。`)
      setPendingInviteCode(''); setNewStudentNameFromInvite('')
      window.history.replaceState({}, '', '/')
      window.location.reload()
    })
  }

  // ============== 预约 ==============
  const fetchAppointments = () => {
    const url = currentRole.includes('老师')
      ? `/api/appointments?teacher_name=${selectedTeacher}`
      : `/api/appointments?patient_name=${selectedPatient}`
    fetch(url).then(r => r.json()).then(d => setAppointments(d)).catch(() => setAppointments([]))
  }

  const handleCreateAppointment = () => {
    if (!apptDate || !apptTime || !apptReason.trim()) {
      alert("请填写完整的预约信息（日期、时间、原因）")
      return
    }
    const initiator = currentRole.includes('老师') ? 'teacher' : 'student'
    fetch('/api/appointments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_name: selectedPatient,
        teacher_name: selectedTeacher,
        initiator,
        scheduled_date: apptDate,
        scheduled_time: apptTime,
        reason: apptReason.trim()
      })
    }).then(() => {
      setShowApptForm(false)
      setApptDate(''); setApptTime(''); setApptReason('')
      fetchAppointments()
    })
  }

  const handleConfirmAppt = (id: number) => {
    fetch(`/api/appointments/${id}/confirm`, { method: 'POST' }).then(() => fetchAppointments())
  }

  const handleCancelAppt = (id: number) => {
    if (!confirm("确定要取消这个预约吗？")) return
    fetch(`/api/appointments/${id}/cancel`, { method: 'POST' }).then(() => fetchAppointments())
  }

  const roleBtnStyle = (role: string): React.CSSProperties => ({
    padding: '8px 16px', margin: '5px', borderRadius: '20px', border: '1px solid #8b4513',
    cursor: 'pointer', fontFamily: 'serif', fontSize: '14px',
    backgroundColor: currentRole === role ? '#8b4513' : '#fdfcf0',
    color: currentRole === role ? '#fff' : '#8b4513', transition: 'all 0.2s'
  })
  const patientBtnStyle = (name: string): React.CSSProperties => ({
    padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px solid #5a7d5a',
    cursor: 'pointer', fontFamily: 'serif', fontSize: '13px',
    backgroundColor: selectedPatient === name ? '#5a7d5a' : '#f7fcf9',
    color: selectedPatient === name ? '#fff' : '#5a7d5a', transition: 'all 0.2s'
  })
  const teacherBtnStyle = (name: string): React.CSSProperties => ({
    padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px solid #8b4513',
    cursor: 'pointer', fontFamily: 'serif', fontSize: '13px',
    backgroundColor: selectedTeacher === name ? '#8b4513' : '#fdfcf0',
    color: selectedTeacher === name ? '#fff' : '#8b4513', transition: 'all 0.2s'
  })

  const needGender = !profile?.gender
  const needBirthDate = !profile?.birth_date
  const needBirthTime = !profile?.birth_time
  const needBirthPlace = !profile?.birth_place

  // 时间段分组
  const morningSlots = ['08:00','08:30','09:00','09:30','10:00','10:30','11:00','11:30']
  const afternoonSlots = ['12:00','12:30','13:00','13:30','14:00','14:30','15:00','15:30','16:00','16:30','17:00','17:30']
  const eveningSlots = ['18:00','18:30','19:00','19:30','20:00']

  const formatSlots = (slots: string[]) => {
    if (!slots || slots.length === 0) return '休息'
    return slots.map(s => s).join('、')
  }

  // ============== 渲染 ==============
  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '40px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>

        {pendingInviteCode && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ background: '#fdfcf0', padding: '24px', borderRadius: '12px', maxWidth: '400px', width: '90%', border: '2px solid #8b4513' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px', textAlign: 'center' }}>🎫 接受老师邀请</div>
              <div style={{ fontSize: '13px', color: '#666', marginBottom: '15px', textAlign: 'center' }}>邀请码：<span style={{ fontFamily: 'monospace', color: '#8b4513', fontWeight: 'bold' }}>{pendingInviteCode}</span></div>
              <input placeholder="请输入您的姓名" value={newStudentNameFromInvite} onChange={e => setNewStudentNameFromInvite(e.target.value)} style={inputStyle} />
              <div style={{ display: 'flex', gap: '10px' }}>
                <button onClick={() => { setPendingInviteCode(''); window.history.replaceState({}, '', '/') }} style={{ flex: 1, padding: '10px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer' }}>取消</button>
                <button onClick={handleAcceptInvite} style={{ flex: 1, padding: '10px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}>加入</button>
              </div>
            </div>
          </div>
        )}

        {previewDraft && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ background: '#fdfcf0', padding: '24px', borderRadius: '12px', maxWidth: '700px', width: '90%', maxHeight: '85vh', overflowY: 'auto', border: '2px solid #8b4513' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px', textAlign: 'center' }}>📄 完整病历预览</div>
              <div style={{ fontSize: '13px', color: '#666', marginBottom: '15px', textAlign: 'center', lineHeight: '1.6' }}>
                请审核，可再编辑一次；<br />
                <span style={{ color: '#c0392b', fontWeight: 'bold' }}>确认签字后，AI 原草案将销毁，音频文件将删除。</span>
              </div>
              <textarea value={previewDraft.content} onChange={e => setPreviewDraft({ ...previewDraft, content: e.target.value })} style={{ width: '100%', minHeight: '400px', padding: '12px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '14px', marginBottom: '15px', boxSizing: 'border-box', whiteSpace: 'pre-wrap', lineHeight: '1.6' }} />
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button onClick={() => setPreviewDraft(null)} style={{ padding: '8px 20px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer' }}>取消（返回修改）</button>
                <button onClick={handleFinalSign} style={{ padding: '8px 24px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontWeight: 'bold' }}>✅ 确认签字</button>
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
              <div style={{ textAlign: 'center', color: '#8b4513', fontSize: '14px', marginBottom: '15px' }}>🌿 {huangli.solar_term_tip}</div>
            )}
            <div style={{ textAlign: 'center', color: '#5a7d5a', fontSize: '16px', marginBottom: '10px' }}>🌿 {huangli.solar_term}：{huangli.health_trend}</div>
            <div style={{ textAlign: 'center', background: '#fff8e7', padding: '15px', borderRadius: '8px', color: '#8b4513' }}>📝 今日作业：{huangli.homework}</div>
          </div>
        )}

        {/* 【第56天新增】智能体工作台（老师端：沉默学生请示闭环） */}
        {(currentRole === '李老师' || currentRole === '李老师智能体') && (
          <div style={boxStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>🤖 智能体工作台</div>
              <button
                onClick={handleAgentScan}
                disabled={scanningAgent}
                style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}
              >{scanningAgent ? '扫描中…' : '🔍 立即扫描'}</button>
            </div>
            {agentTasks.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#999', fontSize: '13px', padding: '8px' }}>暂无待办</div>
            ) : (
              agentTasks.map(task => (
                <div key={task.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px', background: '#fffdf5', border: '1px solid #f0e9d6', borderRadius: '8px', marginBottom: '8px' }}>
                  <div style={{ flex: 1, marginRight: '10px' }}>
                    <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '4px' }}>{task.title}</div>
                    <div style={{ fontSize: '12px', color: '#666', lineHeight: '1.5' }}>{task.content}</div>
                  </div>
                  <div style={{ whiteSpace: 'nowrap' }}>
                    <button onClick={() => handleResolveAgentTask(task.id, 'approved')} style={{ marginRight: '6px', padding: '4px 10px', borderRadius: '4px', border: 'none', background: '#5a7d5a', color: '#fdfcf0', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}>确认执行</button>
                    <button onClick={() => handleResolveAgentTask(task.id, 'rejected')} style={{ padding: '4px 10px', borderRadius: '4px', border: 'none', background: '#d4c8a8', color: '#333', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}>忽略</button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && healthTrend && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>📊 我的健康趋势</div>
            <div style={{ textAlign: 'center', fontSize: '13px', color: '#666', marginBottom: '12px' }}>八字：{healthTrend.bazi}</div>
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
                      <div style={{ width: `${barWidth}%`, height: '100%', background: isWeakest ? '#c0392b' : '#8b4513', borderRadius: '8px', transition: 'width 0.5s' }} />
                    </div>
                    <div style={{ width: '20px', fontSize: '13px', color: '#666', textAlign: 'right' }}>{count}</div>
                  </div>
                )
              })}
            </div>
            <div style={{ textAlign: 'center', padding: '10px', background: '#fff8e7', borderRadius: '8px', marginBottom: '12px' }}>
              <span style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold' }}>☯ 阴阳状态：{healthTrend.yinyang}</span>
            </div>
            <div style={{ padding: '12px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
              <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '5px' }}>💡 体质参考：</div>
              <div style={{ fontSize: '14px', color: '#333', lineHeight: '1.6' }}>{healthTrend.tendency}</div>
            </div>
            <div style={{ textAlign: 'center', fontSize: '11px', color: '#999', marginTop: '10px', fontStyle: 'italic' }}>基于出生八字的先天体质参考，具体辨证请以老师当面问诊为准</div>
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && dailyAdvice && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>🌤️ 今日建议 · {dailyAdvice.solar_term}</div>
            {dailyAdvice.tendency_note && (
              <div style={{ textAlign: 'center', padding: '8px', background: '#fff8e7', borderRadius: '8px', marginBottom: '15px', fontSize: '13px', color: '#8b4513' }}>💡 {dailyAdvice.tendency_note}</div>
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
              <button onClick={() => setShowTeacherPicker(!showTeacherPicker)} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px' }}>
                {showTeacherPicker ? '收起' : '管理'}
              </button>
            </div>
            <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>当前咨询：<span style={{ color: '#8b4513', fontWeight: 'bold' }}>{selectedTeacher}</span></div>
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
            {showTeacherPicker && (
              <div style={{ marginTop: '12px', borderTop: '1px dashed #d4c8a8', paddingTop: '12px' }}>
                <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>可选老师：</div>
                {teachers.filter(t => !patientTeachers.includes(t.name)).map(t => (
                  <button key={t.name} onClick={() => handleAddTeacher(t.name)} style={{ padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px dashed #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '13px' }}>+ {t.name}</button>
                ))}
              </div>
            )}
          </div>
        )}

        {(currentRole === '李老师' || currentRole === '李老师智能体') && (
          <div style={{ ...boxStyle, background: '#f0f7f0' }}>
            <div style={{ fontSize: '18px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>👥 学生管理（{teacherPatients.length}人）</div>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '15px' }}>
              <input id="newStudentInput" placeholder="输入学生姓名，添加为新学生" style={{ flex: 1, padding: '8px', borderRadius: '6px', border: '1px solid #b8d8c0', fontFamily: 'serif' }} />
              <button onClick={() => {
                const input = document.getElementById('newStudentInput') as HTMLInputElement
                const name = input?.value.trim()
                if (!name) { alert("请输入学生姓名"); return }
                fetch('/api/teacher/add-student', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ teacher_name: selectedTeacher, student_name: name }) })
                  .then(() => { input.value = ''; fetch(`/api/teacher-patients?teacher_name=${selectedTeacher}`).then(r => r.json()).then(d => setTeacherPatients(d)); fetchPatients('张三') })
              }} style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer' }}>+ 添加学生</button>
              <button onClick={handleCreateInvite} style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer' }}>🎫 生成邀请码</button>
            </div>

            {invites.length > 0 && (
              <div style={{ marginBottom: '15px', padding: '10px', background: '#fef8f0', borderRadius: '8px', border: '1px dashed #d4c8a8' }}>
                <div style={{ fontSize: '13px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>📮 已生成的邀请码（7天有效）</div>
                {invites.map((inv: any) => (
                  <div key={inv.code} style={{ display: 'flex', alignItems: 'center', padding: '6px', background: '#fff', borderRadius: '6px', marginBottom: '5px', fontSize: '13px' }}>
                    <div style={{ flex: 1, color: '#8b4513', fontWeight: 'bold', fontFamily: 'monospace' }}>{inv.code}</div>
                    <div style={{ flex: 1, fontSize: '11px', color: '#999' }}>{inv.used_by ? `已使用：${inv.used_by}` : '未使用'}</div>
                    {!inv.used_by && (
                      <button onClick={() => handleCopyInviteLink(inv.code)} style={{ padding: '3px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '11px' }}>复制链接</button>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div style={{ background: '#fff', borderRadius: '8px', border: '1px solid #d4e8d4', overflow: 'hidden' }}>
              <div style={{ display: 'flex', padding: '10px', background: '#e8f4e8', fontSize: '13px', fontWeight: 'bold', color: '#5a7d5a' }}>
                <div style={{ flex: 2 }}>学生姓名</div>
                <div style={{ flex: 1, textAlign: 'center' }}>状态</div>
                <div style={{ flex: 1, textAlign: 'right' }}>操作</div>
              </div>
              {teacherPatients.length === 0 ? (
                <div style={{ padding: '20px', textAlign: 'center', color: '#999', fontSize: '13px' }}>暂无学生，请在上方添加</div>
              ) : (
                teacherPatients.map((s: any) => (
                  <div key={s.name} style={{ display: 'flex', alignItems: 'center', padding: '10px', borderTop: '1px solid #f0f0f0', fontSize: '14px' }}>
                    <div style={{ flex: 2, color: '#333' }}>👤 {s.name}</div>
                    <div style={{ flex: 1, textAlign: 'center' }}>
                      <span style={{ padding: '2px 10px', borderRadius: '12px', fontSize: '12px', background: `${s.status_color}15`, color: s.status_color, fontWeight: 'bold', border: `1px solid ${s.status_color}40` }}>{s.status_label}</span>
                    </div>
                    <div style={{ flex: 1, textAlign: 'right' }}>
                      <button style={{ padding: '4px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '12px', marginRight: '6px' }} onClick={() => setSelectedPatient(s.name)}>查看</button>
                      {s.name !== '张三' && s.name !== '李四' && (
                        <button onClick={() => {
                          if (!confirm(`确定要将学生【${s.name}】从您的名单中移除吗？`)) return
                          fetch(`/api/patient-teachers?patient_name=${s.name}&teacher_name=${selectedTeacher}`, { method: 'DELETE' })
                            .then(() => fetch(`/api/teacher-patients?teacher_name=${selectedTeacher}`).then(r => r.json()).then(d => setTeacherPatients(d)))
                        }} style={{ padding: '4px 10px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '12px' }}>移除</button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#f0f7f5' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ fontSize: '18px', color: '#5a7d5a', fontWeight: 'bold' }}>🏠 我的家庭（{patients.length}人）</div>
              <button onClick={handleToggleAddFamily} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '12px' }}>{showAddFamily ? '取消' : '+ 添加亲友'}</button>
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
                <label style={{ fontSize: '12px', color: '#888' }}>出生时间（选填）</label>
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

        {/* 预约卡片（可视化网格） */}
        {(currentRole === '学生' || currentRole === '学生智能体' || currentRole === '李老师' || currentRole === '李老师智能体') && (
          <div style={boxStyle}>
            <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '12px' }}>
              📅 {currentRole.includes('老师') ? '排班与预约管理' : `预约 ${selectedTeacher}`}
            </div>

            {/* 老师工作时间设置 */}
            {currentRole.includes('老师') && schedule && (
              <div style={{ marginBottom: '12px', padding: '10px', background: '#f0f7f0', borderRadius: '8px', border: '1px dashed #5a7d5a' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold' }}>⚙️ 我的工作时间</div>
                  <button onClick={() => setEditingSchedule(!editingSchedule)} style={{ padding: '2px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '11px' }}>
                    {editingSchedule ? '取消' : '修改'}
                  </button>
                </div>
                {!editingSchedule ? (
                  <div style={{ fontSize: '12px', color: '#666', lineHeight: '1.8' }}>
                    {[1,2,3,4,5,6,0].map(d => (
                      <div key={d}>周{['日','一','二','三','四','五','六'][d]}：{formatSlots(schedule[String(d)] || [])}</div>
                    ))}
                  </div>
                ) : (
                  <div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '10px' }}>
                      {[1,2,3,4,5,6,0].map(d => (
                        <button key={d} onClick={() => setScheduleEditDay(String(d))} style={{ padding: '4px 12px', borderRadius: '12px', border: '1px solid #5a7d5a', background: scheduleEditDay === String(d) ? '#5a7d5a' : 'transparent', color: scheduleEditDay === String(d) ? '#fff' : '#5a7d5a', cursor: 'pointer', fontSize: '12px' }}>
                          周{['日','一','二','三','四','五','六'][d]}
                        </button>
                      ))}
                    </div>
                    {[
                      { label: '🌅 上午', slots: morningSlots },
                      { label: '☀️ 下午', slots: afternoonSlots },
                      { label: '🌙 晚间', slots: eveningSlots }
                    ].map(group => (
                      <div key={group.label}>
                        <div style={{ fontSize: '12px', color: '#666', fontWeight: 'bold', marginBottom: '4px' }}>{group.label}</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px', marginBottom: '8px' }}>
                          {group.slots.map(s => (
                            <button key={s} onClick={() => toggleSlot(scheduleEditDay, s)} style={{ padding: '3px 8px', borderRadius: '10px', border: '1px solid #8b4513', background: (tempSchedule[scheduleEditDay] || []).includes(s) ? '#8b4513' : 'transparent', color: (tempSchedule[scheduleEditDay] || []).includes(s) ? '#fff' : '#8b4513', cursor: 'pointer', fontSize: '11px' }}>{s}</button>
                          ))}
                        </div>
                      </div>
                    ))}
                    <div style={{ textAlign: 'right' }}>
                      <button onClick={handleSaveSchedule} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>保存工作时间</button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 节假日管理 */}
            {currentRole.includes('老师') && (
              <div style={{ marginBottom: '12px', padding: '10px', background: '#fff5f5', borderRadius: '8px', border: '1px dashed #c0392b' }}>
                <div style={{ fontSize: '13px', color: '#c0392b', fontWeight: 'bold', marginBottom: '8px' }}>🎌 节假日设置</div>
                <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                  <input type="date" value={newHolidayDate} onChange={e => setNewHolidayDate(e.target.value)} style={{ flex: 1, padding: '6px', borderRadius: '6px', border: '1px solid #c0392b', fontSize: '13px', fontFamily: 'serif' }} />
                  <button onClick={handleAddHoliday} style={{ padding: '6px 14px', borderRadius: '6px', border: 'none', background: '#c0392b', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>+ 添加</button>
                </div>
                {holidays.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {holidays.map(d => (
                      <div key={d} style={{ display: 'flex', alignItems: 'center', padding: '3px 8px', borderRadius: '12px', background: '#fff', border: '1px solid #c0392b', fontSize: '12px' }}>
                        <span style={{ color: '#c0392b' }}>{d}</span>
                        <button onClick={() => handleRemoveHoliday(d)} style={{ marginLeft: '6px', border: 'none', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '14px', padding: 0 }}>×</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 7 天 tab 切换 */}
            {calendarData && calendarData.days && (
              <div>
                <div style={{ display: 'flex', gap: '4px', marginBottom: '12px', overflowX: 'auto' }}>
                  {calendarData.days.map((d: any, i: number) => (
                    <button
                      key={d.date}
                      onClick={() => setSelectedDayIndex(i)}
                      style={{
                        flex: 1, minWidth: '64px', padding: '8px 4px', borderRadius: '8px',
                        border: selectedDayIndex === i ? '1px solid #8b4513' : '1px solid #d4c8a8',
                        background: selectedDayIndex === i ? '#8b4513' : '#fff',
                        color: selectedDayIndex === i ? '#fff' : '#333',
                        cursor: 'pointer', fontSize: '12px', fontFamily: 'serif'
                      }}
                    >
                      <div style={{ fontWeight: 'bold' }}>周{['日','一','二','三','四','五','六'][d.weekday]}</div>
                      <div style={{ fontSize: '10px', opacity: 0.8, marginTop: '2px' }}>{d.date.slice(5)}</div>
                    </button>
                  ))}
                </div>

                {/* 时段网格 */}
                {(() => {
                  const day = calendarData.days[selectedDayIndex]
                  if (!day) return null
                  if (day.is_holiday) {
                    return <div style={{ textAlign: 'center', padding: '20px', color: '#c0392b', background: '#fff5f5', borderRadius: '8px' }}>🎌 老师今日休息</div>
                  }
                  if (!day.slots || day.slots.length === 0) {
                    return <div style={{ textAlign: 'center', padding: '20px', color: '#999', background: '#f5f5f5', borderRadius: '8px' }}>老师今日无排班</div>
                  }
                  return (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px' }}>
                      {[...day.slots].sort().map((slot: string) => {
                        const booked = day.booked[slot]
                        const isTeacher = currentRole.includes('老师')
                        return (
                          <button
                            key={slot}
                            onClick={() => {
                              if (booked) return
                              setApptDate(day.date)
                              setApptTime(slot)
                              setShowApptForm(true)
                            }}
                            disabled={!!booked}
                            style={{
                              padding: '10px 4px', borderRadius: '6px',
                              border: booked ? '1px solid #c0392b' : '1px solid #5a7d5a',
                              background: booked ? '#fdf0f0' : '#f7fcf9',
                              color: booked ? '#c0392b' : '#5a7d5a',
                              cursor: booked ? 'not-allowed' : 'pointer',
                              fontSize: '12px', fontFamily: 'serif', textAlign: 'center'
                            }}
                          >
                            <div style={{ fontWeight: 'bold' }}>{slot}</div>
                            <div style={{ fontSize: '10px', marginTop: '2px' }}>
                              {booked ? `${booked.patient_name} ${booked.status === 'confirmed' ? '✅' : '⏳'}` : (isTeacher ? '空闲' : '可约')}
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  )
                })()}

                {/* 老师端待处理 */}
                {currentRole.includes('老师') && (
                  <div style={{ marginTop: '15px' }}>
                    <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📋 待处理预约</div>
                    {appointments.filter((a: any) => a.status === 'pending').length === 0 ? (
                      <div style={{ fontSize: '12px', color: '#999', textAlign: 'center', padding: '10px' }}>暂无</div>
                    ) : (
                      appointments.filter((a: any) => a.status === 'pending').map((a: any) => (
                        <div key={a.id} style={{ padding: '10px', background: '#fff8e7', borderRadius: '6px', marginBottom: '6px', fontSize: '12px' }}>
                          <div style={{ color: '#8b4513', fontWeight: 'bold' }}>{a.scheduled_date} · {a.scheduled_time}</div>
                          <div style={{ color: '#666', marginTop: '3px' }}>患者：{a.patient_name} · 原因：{a.reason}</div>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '6px', justifyContent: 'flex-end' }}>
                            <button onClick={() => handleConfirmAppt(a.id)} style={{ padding: '3px 12px', borderRadius: '12px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '11px' }}>确认</button>
                            <button onClick={() => handleCancelAppt(a.id)} style={{ padding: '3px 12px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>取消</button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {/* 学生端预约记录 */}
                {!currentRole.includes('老师') && appointments.length > 0 && (
                  <div style={{ marginTop: '15px' }}>
                    <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📋 我的预约记录</div>
                    {appointments.map((a: any) => (
                      <div key={a.id} style={{ padding: '8px', background: '#fff', borderRadius: '6px', marginBottom: '5px', fontSize: '12px', border: '1px solid #e0e0e0' }}>
                        <span style={{ color: '#8b4513', fontWeight: 'bold' }}>{a.scheduled_date} · {a.scheduled_time}</span>
                        <span style={{ float: 'right' }}>
                          {a.status === 'confirmed' ? '✅ 已确认' : a.status === 'cancelled' ? '❌ 已取消' : '⏳ 待确认'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 预约表单 */}
            {showApptForm && (
              <div style={{ marginTop: '15px', padding: '12px', background: '#fffaf0', borderRadius: '8px', border: '1px dashed #d4c8a8' }}>
                <div style={{ fontSize: '13px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>
                  确认预约：{apptDate} · {apptTime}
                </div>
                <textarea
                  placeholder="预约原因（如：复诊/症状变化/家人新症状...）"
                  value={apptReason}
                  onChange={e => setApptReason(e.target.value)}
                  style={{ width: '100%', height: '60px', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '13px', marginBottom: '8px', boxSizing: 'border-box' }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                  <button onClick={() => { setShowApptForm(false); setApptDate(''); setApptTime(''); setApptReason('') }} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontSize: '12px' }}>取消</button>
                  <button onClick={handleCreateAppointment} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '12px' }}>提交预约</button>
                </div>
              </div>
            )}
          </div>
        )}

        <div style={boxStyle}>
                  {/* 【第51天新增】中药材库存 */}
        {(currentRole === '李老师' || currentRole === '李老师智能体') && (
          <div style={boxStyle}>
            <h3 style={{ color: '#8b4513', textAlign: 'center', marginBottom: '12px' }}>💊 中药材库存</h3>
            <div style={{ marginBottom: '12px' }}>
              <button
                onClick={() => setShowHerbForm(true)}
                style={{ marginRight: '8px', background: '#8b4513', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}
              >+ 新增药材</button>
              <button
                onClick={toggleLowOnly}
                style={{ background: showLowOnly ? '#c0392b' : '#5a7d5a', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}
              >{showLowOnly ? '显示全部' : '查看预警'}</button>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'serif' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #d4c8a8' }}>
                  <th style={{ textAlign: 'left', padding: '6px' }}>药材名</th>
                  <th style={{ textAlign: 'left', padding: '6px' }}>库存</th>
                  <th style={{ textAlign: 'left', padding: '6px' }}>单位</th>
                  <th style={{ textAlign: 'left', padding: '6px' }}>预警</th>
                  <th style={{ textAlign: 'left', padding: '6px' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {herbs.map(h => (
                  <tr key={h.id} style={{ borderBottom: '1px solid #d4c8a8', color: h.is_low ? '#c0392b' : 'inherit' }}>
                    <td style={{ padding: '6px' }}>{h.is_low ? '⚠️ ' : ''}{h.herb_name}</td>
                    <td style={{ padding: '6px' }}>{h.stock_amount}</td>
                    <td style={{ padding: '6px' }}>{h.unit}</td>
                    <td style={{ padding: '6px' }}>{h.warn_threshold}</td>
                    <td style={{ padding: '6px' }}>
                      <button onClick={() => openAdjustModal(h)} style={{ marginRight: '6px', cursor: 'pointer' }}>调整</button>
                      <button onClick={() => handleDeleteHerb(h.id)} style={{ cursor: 'pointer' }}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {showHerbForm && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ ...boxStyle, width: '320px' }}>
              <h4 style={{ color: '#8b4513' }}>新增 / 更新药材</h4>
              <input style={inputStyle} placeholder="药材名" value={herbForm.herb_name} onChange={e => setHerbForm({ ...herbForm, herb_name: e.target.value })} />
              <input style={inputStyle} type="number" placeholder="库存量" value={herbForm.stock_amount} onChange={e => setHerbForm({ ...herbForm, stock_amount: e.target.value })} />
              <input style={inputStyle} placeholder="单位" value={herbForm.unit} onChange={e => setHerbForm({ ...herbForm, unit: e.target.value })} />
              <input style={inputStyle} type="number" placeholder="预警阈值" value={herbForm.warn_threshold} onChange={e => setHerbForm({ ...herbForm, warn_threshold: e.target.value })} />
              <div style={{ marginTop: '12px' }}>
                <button onClick={handleSaveHerb} style={{ marginRight: '8px', background: '#8b4513', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}>保存</button>
                <button onClick={() => setShowHerbForm(false)} style={{ background: '#d4c8a8', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}>取消</button>
              </div>
            </div>
          </div>
        )}

        {adjustingHerb && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ ...boxStyle, width: '280px' }}>
              <h4 style={{ color: '#8b4513' }}>调整库存：{adjustingHerb.herb_name}</h4>
              <p>当前库存：{adjustingHerb.stock_amount} {adjustingHerb.unit}</p>
              <input style={inputStyle} type="number" placeholder="入库填正数，出库填负数" value={adjustDelta} onChange={e => setAdjustDelta(parseFloat(e.target.value) || 0)} />
              <div style={{ marginTop: '12px' }}>
                <button onClick={submitAdjust} style={{ marginRight: '8px', background: '#8b4513', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}>确认</button>
                <button onClick={() => setAdjustingHerb(null)} style={{ background: '#d4c8a8', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}>取消</button>
              </div>
            </div>
          </div>
        )}

        {/* 【第52天新增】开方（中药材首字联想 + 结构化存储） */}
        {(currentRole === '李老师' || currentRole === '李老师智能体') && (
          <div style={boxStyle}>
            <h3 style={{ color: '#8b4513', textAlign: 'center', marginBottom: '12px' }}>📝 开方</h3>
            <input
              style={inputStyle}
              placeholder="患者姓名"
              value={prescriptionPatient}
              onChange={e => setPrescriptionPatient(e.target.value)}
            />
            {/* 【第53天新增】远程诊疗开关：勾选则不扣老师库存 */}
            <label style={{ display: 'flex', alignItems: 'center', fontFamily: 'serif', color: '#5a7d5a', marginBottom: '12px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={prescriptionRemote}
                onChange={e => setPrescriptionRemote(e.target.checked)}
                style={{ marginRight: '6px' }}
              />
              远程诊疗（学生自采，不扣库存）
            </label>
            {prescriptionItems.map((item, index) => (
              <div key={index} style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <div style={{ flex: 2, position: 'relative' }}>
                  <input
                    style={{ ...inputStyle, marginBottom: 0 }}
                    placeholder="药材名（输入首字联想）"
                    value={item.herb_name}
                    onChange={e => changePrescriptionItem(index, 'herb_name', e.target.value)}
                  />
                  {(herbSuggestions[index] || []).length > 0 && (
                    <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#fffdf5', border: '1px solid #d4c8a8', borderRadius: '4px', zIndex: 20, maxHeight: '160px', overflowY: 'auto' }}>
                      {(herbSuggestions[index] || []).map(h => (
                        <div
                          key={h.id}
                          onClick={() => pickHerbSuggestion(index, h)}
                          style={{ padding: '6px 8px', cursor: 'pointer', fontFamily: 'serif', borderBottom: '1px solid #f0e9d6' }}
                        >
                          {h.herb_name}（库存 {h.stock_amount}{h.unit}）
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <input
                  style={{ ...inputStyle, marginBottom: 0, width: '90px' }}
                  type="number"
                  placeholder="克数"
                  value={item.amount}
                  onChange={e => changePrescriptionItem(index, 'amount', e.target.value)}
                />
                {/* 【第54天新增】固定单位标签（暂不支持切换单位） */}
                <span style={{ alignSelf: 'center', color: '#999', fontSize: '13px', fontFamily: 'serif' }}>克</span>
              </div>
            ))}
            <div style={{ marginTop: '12px' }}>
              <button
                onClick={addPrescriptionItem}
                style={{ marginRight: '8px', background: '#5a7d5a', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}
              >+ 添加一味药</button>
              <button
                onClick={handleSavePrescription}
                disabled={savingPrescription}
                style={{ background: '#8b4513', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}
              >{savingPrescription ? '保存中...' : '保存药方'}</button>
            </div>
          </div>
        )}

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
            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              <button onClick={handleCheckIn} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>立即打卡（+10积分）</button>
            </div>
          )}
          {currentRole === '李老师' && roleData?.task === '待审核' && roleData?.detail.includes('已打卡') && (
            <div style={{ textAlign: 'center', marginTop: '20px' }}>
              <button onClick={handleApprove} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#5a7d5a', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>签字确认</button>
            </div>
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
              <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontWeight: 'bold' }}>八字：{profile.bazi || '缺少出生日期，无法推算'}</div>
              {profile.wuxing && (<div style={{ color: '#5a7d5a', fontWeight: 'bold' }}>五行体质参考：{profile.wuxing}</div>)}
            </div>
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '15px' }}>🗣️ 学生智能体（先结构化，再发送）</div>
            <textarea value={inputText} onChange={(e) => setInputText(e.target.value)} placeholder="在此输入您的感受、症状，或点下方🎤录音..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '10px', boxSizing: 'border-box' }} />
            <div style={{ marginBottom: '15px', textAlign: 'center' }}>
              <button onClick={startStudentRecording} style={{ padding: '8px 24px', borderRadius: '30px', border: 'none', background: isRecordingStudent ? '#c0392b' : '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '14px', fontFamily: 'serif' }}>
                {isRecordingStudent ? '⏹ 停止录音（点击结束）' : '🎤 开始录音'}
              </button>
              {isRecordingStudent && (<div style={{ fontSize: '12px', color: '#c0392b', marginTop: '5px' }}>● 正在录音，请说话...（说完再点一次停止）</div>)}
            </div>
            {pendingAudios.length > 0 && (
              <div style={{ marginBottom: '15px', padding: '10px', border: '1px dashed #b8d8c0', borderRadius: '8px', background: '#f7fcf9' }}>
                <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>🎙️ 待发送的录音（{pendingAudios.length}段）</div>
                {pendingAudios.map((url, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', marginBottom: '5px' }}>
                    <audio src={url} controls style={{ flex: 1, height: '30px' }} />
                    <button onClick={() => setPendingAudios(prev => prev.filter(u => u !== url))} style={{ marginLeft: '8px', padding: '2px 8px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>删除</button>
                  </div>
                ))}
              </div>
            )}
            {pendingImages.length > 0 && (
              <div style={{ marginBottom: '15px', padding: '10px', border: '1px dashed #b8d8c0', borderRadius: '8px', background: '#f7fcf9' }}>
                <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📎 待发送的图片（{pendingImages.length}张）</div>
                <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                  {pendingImages.map((url, i) => (
                    <div key={i} style={{ position: 'relative', margin: '4px' }}>
                      <img src={url} alt={`待发送${i + 1}`} style={{ width: '100px', height: '100px', objectFit: 'cover', borderRadius: '8px', border: '1px solid #b8d8c0' }} />
                      <button onClick={() => handleRemovePendingImage(url)} style={{ position: 'absolute', top: '2px', right: '2px', width: '22px', height: '22px', borderRadius: '50%', border: 'none', background: '#c0392b', color: '#fff', cursor: 'pointer', fontSize: '12px', lineHeight: '22px', padding: 0 }}>✕</button>
                    </div>
                  ))}
                </div>
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
                <textarea value={structuredPreview} onChange={(e) => setStructuredPreview(e.target.value)} style={{ width: '100%', height: '150px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#f7fcf9', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box' }} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                  <button onClick={() => setStructuredPreview(null)} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontSize: '13px' }}>取消</button>
                  <button onClick={handleConfirmSend} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>确认发送给 {selectedTeacher}</button>
                </div>
              </div>
            )}
          </div>
        )}

        {(currentRole === '李老师' || currentRole === '李老师智能体') && (
          <div style={{ ...boxStyle, background: '#fcfdfa' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '15px' }}>📄 病历草案（老师智能体生成，待老师补充）</div>
            {drafts.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#999' }}>暂无待处理病历</div>
            ) : (
              drafts.map(d => (
                <div key={d.id} style={{ padding: '15px', border: '1px solid #e0e0e0', borderRadius: '8px', marginBottom: '15px', background: '#fff' }}>
                  <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '5px' }}>学生：{d.patient_name}</div>
                  <textarea value={d.content} onChange={(e) => { setDrafts(drafts.map(item => item.id === d.id ? { ...item, content: e.target.value } : item)) }} style={{ width: '100%', height: '180px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box', whiteSpace: 'pre-wrap' }} />
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
                    <button onClick={() => handleEditDraft(d.id, d.content)} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer' }}>保存病历修改</button>
                  </div>

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

                  {extractAudioUrls(d.content).length > 0 && (
                    <div style={{ marginBottom: '15px', padding: '10px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
                      <div style={{ fontSize: '12px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>🎙️ 学生录音：</div>
                      {extractAudioUrls(d.content).map((url, i) => (
                        <audio key={i} src={url} controls style={{ width: '100%', marginBottom: '5px' }} />
                      ))}
                    </div>
                  )}

                  <div style={{ marginTop: '15px', padding: '12px', background: '#f0f7f0', borderRadius: '8px', border: '1px dashed #5a7d5a' }}>
                    <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>📸 现场辅助记录（老师口述 → AI整理）</div>
                    <textarea placeholder="点击下方 🎤 录音，口述望闻问切内容；或直接打字..." value={teacherLiveText[d.id] || ''} onChange={e => setTeacherLiveText(prev => ({ ...prev, [d.id]: e.target.value }))} style={{ width: '100%', minHeight: '100px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#fff', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box' }} />
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                      <button onClick={() => startTeacherLiveRecording(d.id)} style={{ flex: 1, padding: '8px', borderRadius: '20px', border: 'none', background: teacherLiveRecording === d.id ? '#c0392b' : '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>
                        {teacherLiveRecording === d.id ? '⏹ 停止录音' : '🎤 开始录音'}
                      </button>
                      <button onClick={() => handleTeacherStructurize(d.id)} disabled={teacherLiveStructurizing[d.id]} style={{ flex: 1, padding: '8px', borderRadius: '20px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '13px' }}>
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

                  <div style={{ marginTop: '10px', padding: '10px', background: '#fffaf0', borderRadius: '8px', border: '1px dashed #d4c8a8' }}>
                    <div style={{ fontSize: '13px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>🏷️ 病历标签（用于知识库归类）</div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <input placeholder="部位（如：舌苔/皮肤/面色）" value={draftTags[d.id]?.area || ''} onChange={e => setDraftTags(prev => ({ ...prev, [d.id]: { area: e.target.value, symptom: prev[d.id]?.symptom || '' } }))} style={{ flex: 1, padding: '6px', borderRadius: '6px', border: '1px solid #d4c8a8', fontSize: '13px', fontFamily: 'serif' }} />
                      <input placeholder="症状（如：湿/热/虚/瘀）" value={draftTags[d.id]?.symptom || ''} onChange={e => setDraftTags(prev => ({ ...prev, [d.id]: { area: prev[d.id]?.area || '', symptom: e.target.value } }))} style={{ flex: 1, padding: '6px', borderRadius: '6px', border: '1px solid #d4c8a8', fontSize: '13px', fontFamily: 'serif' }} />
                    </div>
                  </div>

                  <div style={{ borderTop: '1px dashed #d4c8a8', paddingTop: '15px', marginTop: '15px' }}>
                    <div style={{ color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📝 给 {d.patient_name} 的辨证施治方案（学生会看到这里的内容）</div>
                    <textarea value={finalPlans[d.id] || ''} onChange={(e) => setFinalPlans({ ...finalPlans, [d.id]: e.target.value })} placeholder="例：抓药xxx，三碗水煲成一碗，饭后服；或今日宜喝姜茶，多休息..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#f7fcf9', fontFamily: 'serif', fontSize: '14px', marginBottom: '10px', boxSizing: 'border-box' }} />
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <button onClick={() => handlePreviewFullRecord(d.id)} style={{ padding: '8px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontWeight: 'bold' }}>📄 预览完整病历</button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

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