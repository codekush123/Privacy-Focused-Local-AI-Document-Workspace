import { useState } from 'react'
import { api, RequestError } from '../services/api'
import { Progress } from './Progress'
import type { AnswerRecord, DocumentSummary, GradeResult, QuestionType, QuizSpec } from '../types/api'

interface Props {
  documents: DocumentSummary[]
  selectedIds: string[]
  ready: boolean
  onExportCreated: () => Promise<void>
  notify: (msg: string, kind?: 'error' | 'info') => void
}

const TYPE_LABEL: Record<QuestionType, string> = { multiple_choice: 'Multiple choice', true_false: 'True / false', short_answer: 'Short answer' }

/**
 * Interactive study session: the AI writes a quiz from the selected documents,
 * the student answers one question at a time, closed questions are graded by
 * rules and free-text answers by the AI tutor with feedback.
 */
export function StudyPanel({ documents, selectedIds, ready, onExportCreated, notify }: Props) {
  const [count, setCount] = useState(6)
  const [types, setTypes] = useState<QuestionType[]>(['multiple_choice', 'true_false', 'short_answer'])
  const [difficulty, setDifficulty] = useState('mixed')
  const [quiz, setQuiz] = useState<QuizSpec | null>(null)
  const [idx, setIdx] = useState(0)
  const [answer, setAnswer] = useState('')
  const [grade, setGrade] = useState<GradeResult | null>(null)
  const [records, setRecords] = useState<AnswerRecord[]>([])
  const [busy, setBusy] = useState<'quiz' | 'grade' | 'report' | null>(null)
  const [finished, setFinished] = useState(false)
  const [runStart, setRunStart] = useState<number | null>(null)
  const selectedDocs = documents.filter((d) => selectedIds.includes(d.id))

  const toggleType = (t: QuestionType) =>
    setTypes((ts) => (ts.includes(t) ? (ts.length > 1 ? ts.filter((x) => x !== t) : ts) : [...ts, t]))

  const start = async () => {
    if (!selectedIds.length) { notify('Select at least one document first.'); return }
    setBusy('quiz'); setRunStart(Date.now())
    setQuiz(null); setRecords([]); setIdx(0); setGrade(null); setAnswer(''); setFinished(false)
    try {
      const q = await api.studyQuiz(selectedIds, count, types, difficulty)
      if (!q.questions.length) { notify('The model returned no questions – try again or select other documents.'); return }
      setQuiz(q)
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(null)
    }
  }

  const submit = async () => {
    if (!quiz) return
    const q = quiz.questions[idx]
    setBusy('grade'); setRunStart(Date.now())
    try {
      const g = await api.studyGrade(q, answer)
      setGrade(g)
      setRecords((r) => [...r, {
        question: q.question, type: q.type, user_answer: answer, correct_answer: q.answer,
        correct: g.correct, score: g.score, feedback: g.feedback, source: q.source,
      }])
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(null)
    }
  }

  const next = () => {
    if (!quiz) return
    if (idx + 1 >= quiz.questions.length) { setFinished(true); return }
    setIdx(idx + 1); setAnswer(''); setGrade(null)
  }

  const exportReport = async (kind: 'xlsx' | 'docx') => {
    setBusy('report')
    try {
      const info = await api.studyReport(quiz?.title ?? 'Study session', records, selectedIds, kind)
      await onExportCreated()
      notify(`Report saved as ${info.filename} – see Exports`, 'info')
    } catch (e) {
      notify((e as RequestError).message)
    } finally {
      setBusy(null)
    }
  }

  const q = quiz?.questions[idx]
  const scoreTotal = records.reduce((a, r) => a + r.score, 0)
  const avg = records.length ? Math.round(scoreTotal / records.length) : 0
  const correctCount = records.filter((r) => r.correct).length

  return (
    <section className="card study">
      <header className="panel-header">
        <h2>Study mode</h2>
        <span className="muted small">{selectedDocs.length ? `From ${selectedDocs.map((d) => d.display_name).join(', ')}` : 'Select documents on the left'}</span>
      </header>

      {busy === 'quiz' && runStart && <Progress phase="Writing the quiz" hint="reading your documents first" since={runStart} />}
      {busy === 'grade' && runStart && <Progress phase="Grading your answer" since={runStart} />}

      {!quiz && (
        <div className="col">
          <p className="muted">The AI writes a quiz from your documents, you answer one question at a time, and the AI grades your free-text answers like a tutor – with feedback and a source for every question.</p>
          <div className="row wrap">
            <label className="field"><span>Questions</span><input type="number" min={1} max={25} value={count} onChange={(e) => setCount(Number(e.target.value))} /></label>
            <label className="field"><span>Difficulty</span>
              <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                {['mixed', 'easy', 'medium', 'hard'].map((d) => <option key={d}>{d}</option>)}
              </select>
            </label>
            <div className="field"><span>Question types</span>
              <div className="row wrap">
                {(Object.keys(TYPE_LABEL) as QuestionType[]).map((t) => (
                  <label key={t} className="check"><input type="checkbox" checked={types.includes(t)} onChange={() => toggleType(t)} />{TYPE_LABEL[t]}</label>
                ))}
              </div>
            </div>
          </div>
          <button className="btn primary" onClick={start} disabled={!ready || busy === 'quiz' || !selectedIds.length}>
            {busy === 'quiz' ? 'Writing quiz… (local model)' : 'Start study session'}
          </button>
          {!ready && <div className="notice error small">llama-server is not connected.</div>}
        </div>
      )}

      {quiz && q && !finished && (
        <div className="study-q">
          <div className="row between small muted">
            <span>{quiz.title}</span>
            <span>Question {idx + 1} of {quiz.questions.length} · {TYPE_LABEL[q.type]} · {q.difficulty}</span>
          </div>
          <div className="meter"><span style={{ width: `${Math.round((idx / quiz.questions.length) * 100)}%` }} /></div>
          <h3 className="question">{q.question}</h3>

          {q.type !== 'short_answer' ? (
            <div className="options">
              {q.options.map((o) => (
                <label key={o} className={`option ${answer === o ? 'chosen' : ''} ${grade ? (o === q.answer ? 'right' : answer === o ? 'wrong' : '') : ''}`}>
                  <input type="radio" name="opt" value={o} checked={answer === o} disabled={!!grade} onChange={() => setAnswer(o)} />
                  {o}
                </label>
              ))}
            </div>
          ) : (
            <textarea rows={3} value={answer} disabled={!!grade} onChange={(e) => setAnswer(e.target.value)} placeholder="Type your answer in your own words…" />
          )}

          {!grade ? (
            <div className="row">
              <button className="btn primary" onClick={submit} disabled={busy === 'grade' || (!answer && q.type !== 'short_answer')}>
                {busy === 'grade' ? 'Grading… (AI tutor)' : 'Check answer'}
              </button>
              <button className="btn" onClick={() => { setAnswer(''); void submit() }} disabled={busy === 'grade'}>Skip</button>
            </div>
          ) : (
            <div className={`notice ${grade.correct ? 'good' : 'error'}`}>
              <strong>{grade.correct ? 'Correct' : grade.score > 0 ? `Partly correct (${grade.score}%)` : 'Incorrect'}</strong>
              <span className="muted small"> · graded by {grade.graded_by === 'ai' ? 'the AI tutor' : 'answer key'}</span>
              <div>{grade.feedback}</div>
              {q.type === 'short_answer' && <div className="small">Reference answer: {q.answer}</div>}
              {q.source && <div className="small muted">Source: {q.source}</div>}
              <button className="btn primary small" onClick={next}>{idx + 1 >= quiz.questions.length ? 'Finish' : 'Next question'}</button>
            </div>
          )}
        </div>
      )}

      {finished && (
        <div className="study-result">
          <h3>Session complete</h3>
          <div className="row">
            <div className="score-big">{avg}%</div>
            <div className="muted">average score · {correctCount} of {records.length} correct</div>
          </div>
          <table className="data">
            <thead><tr><th>#</th><th>Question</th><th>Your answer</th><th>Result</th></tr></thead>
            <tbody>
              {records.map((r, i) => (
                <tr key={i}>
                  <td>{i + 1}</td><td>{r.question}</td><td>{r.user_answer || <span className="muted">–</span>}</td>
                  <td><span className={`verdict ${r.correct ? 'supported' : r.score > 0 ? 'partially_supported' : 'contradicted'}`}>{r.score}%</span></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row wrap">
            <button className="btn primary" onClick={() => exportReport('xlsx')} disabled={busy === 'report'}>Export results (Excel)</button>
            <button className="btn" onClick={() => exportReport('docx')} disabled={busy === 'report'}>Export report (Word)</button>
            <button className="btn" onClick={() => { setQuiz(null); setFinished(false) }}>New session</button>
          </div>
        </div>
      )}
    </section>
  )
}
