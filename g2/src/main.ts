import {
  waitForEvenAppBridge,
  TextContainerProperty,
  ImageContainerProperty,
  ImageRawDataUpdate,
  CreateStartUpPageContainer,
  TextContainerUpgrade,
  OsEventTypeList,
} from '@evenrealities/even_hub_sdk'

// Override for laptop work: VITE_PI_WS=ws://localhost:8765/ws npm run dev
const PI_WS =
  import.meta.env.VITE_PI_WS ??
  'ws://10.183.65.133:8765/ws'

const bridge = await waitForEvenAppBridge()

// ==================================================
// APP STATE
// ==================================================

let mode = 'surround'

let socket: WebSocket | null = null
let shuttingDown = false

let lastCaption = ''
let lastStatus = ''

// ==================================================
// RADAR SETTINGS
// ==================================================

const RADAR_W = 140
const RADAR_H = 140

// 12 positions around the wearer.
const SECTOR_SIZE = 30

// ==================================================
// SOUND HOLD
//
// G2 image transfer is much slower than the Pi's
// sound classifier.
//
// Example:
//
// HORN detected
// ALARM detected 0.3 s later
//
// Without a hold, HORN may disappear before the
// bitmap reaches the glasses.
//
// We therefore hold the best detection.
// ==================================================

const SOUND_HOLD_MS = 3000

let heldSound = ''
let heldSoundScore = 0

let heldSoundAngle:
  number | null = null

let heldSoundUntil = 0

// ==================================================
// UI
// ==================================================

const header =
  new TextContainerProperty({
    xPosition: 0,
    yPosition: 0,

    width: 576,
    height: 42,

    borderWidth: 0,
    borderColor: 5,

    paddingLength: 4,

    containerID: 1,
    containerName: 'header',

    content: 'SONA | SURROUND',

    isEventCapture: 0,
  })

const caption =
  new TextContainerProperty({
    xPosition: 160,
    yPosition: 50,

    width: 410,
    height: 165,

    borderWidth: 0,
    borderColor: 5,

    paddingLength: 6,

    containerID: 2,
    containerName: 'caption',

    content: 'Connecting...',

    isEventCapture: 1,
  })

const status =
  new TextContainerProperty({
    xPosition: 0,
    yPosition: 230,

    width: 576,
    height: 45,

    borderWidth: 0,
    borderColor: 5,

    paddingLength: 4,

    containerID: 3,
    containerName: 'status',

    content: 'PI: CONNECTING',

    isEventCapture: 0,
  })

const radar =
  new ImageContainerProperty({
    xPosition: 5,
    yPosition: 55,

    width: RADAR_W,
    height: RADAR_H,

    containerID: 4,
    containerName: 'radar',
  })

await bridge.createStartUpPageContainer(
  new CreateStartUpPageContainer({
    containerTotalNum: 4,

    textObject: [
      header,
      caption,
      status,
    ],

    imageObject: [
      radar,
    ],
  }),
)

// ==================================================
// TEXT UPDATES
// ==================================================

let textQueue:
  Promise<unknown> =
  Promise.resolve()

function updateText(
  id: number,
  name: string,
  content: string,
) {
  textQueue =
    textQueue.then(() =>
      bridge.textContainerUpgrade(
        new TextContainerUpgrade({
          containerID: id,
          containerName: name,
          content,
        }),
      ),
    )

  return textQueue
}

function setCaption(
  text: string,
) {
  if (!text) return

  if (
    text ===
    lastCaption
  ) {
    return
  }

  lastCaption =
    text

  updateText(
    2,
    'caption',
    text.slice(-200),
  )
}

function setStatus(
  text: string,
) {
  if (
    text ===
    lastStatus
  ) {
    return
  }

  lastStatus =
    text

  updateText(
    3,
    'status',
    text,
  )
}

function setMode(
  newMode: string,
) {
  if (
    newMode === mode
  ) {
    return
  }

  mode =
    newMode

  updateText(
    1,
    'header',
    `SONA | ${mode.toUpperCase()}`,
  )
}

// ==================================================
// ANGLE
// ==================================================

function normalizeAngle(
  angle: number,
): number {
  return (
    (
      angle % 360
    ) + 360
  ) % 360
}

function quantizeAngle(
  angle: number,
): number {
  const normalized =
    normalizeAngle(
      angle,
    )

  return (
    Math.round(
      normalized /
      SECTOR_SIZE,
    ) *
    SECTOR_SIZE
  ) % 360
}

// ==================================================
// SOUND LABEL
// ==================================================

function cleanSoundLabel(
  label: string | null,
): string {
  if (!label) {
    return ''
  }

  const result =
    label
      .toUpperCase()
      .trim()

  return result.slice(
    0,
    10,
  )
}

// ==================================================
// DRAW RADAR
// ==================================================

async function createRadarBitmap(
  angle: number | null,
  soundLabel: string | null,
): Promise<Uint8Array> {

  const canvas =
    document.createElement(
      'canvas',
    )

  canvas.width =
    RADAR_W

  canvas.height =
    RADAR_H

  const ctx =
    canvas.getContext(
      '2d',
    )

  if (!ctx) {
    throw new Error(
      'Canvas unavailable',
    )
  }

  ctx.clearRect(
    0,
    0,
    RADAR_W,
    RADAR_H,
  )

  const cx =
    RADAR_W / 2

  const cy =
    RADAR_H / 2

  // Ring geometry: one ring, the bearing dot just inside it,
  // the sound label in the middle.
  // (Design from sona_glasses/sona/display/renderer.py.)
  const radius = 62
  const dotR = 8

  // RING
  ctx.strokeStyle = '#ffffff'
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.stroke()

  // FRONT MARKER: small triangle inside the ring, pointing in
  ctx.fillStyle = '#ffffff'
  ctx.beginPath()
  ctx.moveTo(cx - 6, cy - radius + 1)
  ctx.lineTo(cx + 6, cy - radius + 1)
  ctx.lineTo(cx, cy - radius + 11)
  ctx.closePath()
  ctx.fill()

  // BEARING DOT (0 deg = front / up, clockwise)
  if (angle !== null && Number.isFinite(angle)) {
    const a = (angle % 360) * Math.PI / 180
    const rr = radius - dotR - 4
    const x = cx + Math.sin(a) * rr
    const y = cy - Math.cos(a) * rr
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(x, y, dotR, 0, Math.PI * 2)
    ctx.fill()
  }

  // CENTRE: the sound label, or a small user dot
  const label = cleanSoundLabel(soundLabel)

  if (label) {
    ctx.fillStyle = '#ffffff'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    if (label.length <= 5) {
      ctx.font = 'bold 25px sans-serif'
    } else if (label.length <= 7) {
      ctx.font = 'bold 21px sans-serif'
    } else {
      ctx.font = 'bold 17px sans-serif'
    }
    ctx.fillText(label, cx, cy)
  } else {
    ctx.fillStyle = '#ffffff'
    ctx.beginPath()
    ctx.arc(cx, cy, 4, 0, Math.PI * 2)
    ctx.fill()
  }

  // ==================================================
  // PNG
  // ==================================================

  const blob =
    await new Promise<Blob>(
      (
        resolve,
        reject,
      ) => {
        canvas.toBlob(
          result => {
            if (result) {
              resolve(
                result,
              )
            } else {
              reject(
                new Error(
                  'PNG generation failed',
                ),
              )
            }
          },

          'image/png',
        )
      },
    )

  const buffer =
    await blob.arrayBuffer()

  return new Uint8Array(
    buffer,
  )
}

// ==================================================
// LATEST-WINS BITMAP SENDER
// ==================================================

type RadarRequest = {
  sector:
    number | null

  sound:
    string
}

let bitmapBusy =
  false

let pendingRadar:
  RadarRequest | null =
    null

let lastRenderedSector:
  number | null =
    null

let lastRenderedSound =
  ''

async function renderLatestRadar() {

  if (
    bitmapBusy
  ) {
    return
  }

  bitmapBusy =
    true

  try {
    while (
      pendingRadar
    ) {
      const request =
        pendingRadar

      pendingRadar =
        null

      console.log(
        'RADAR SEND',
        {
          sector:
            request.sector,

          sound:
            request.sound,
        },
      )

      const bytes =
        await createRadarBitmap(
          request.sector,
          request.sound || null,
        )

      const result =
        await bridge.updateImageRawData(
          new ImageRawDataUpdate({
            containerID: 4,

            containerName:
              'radar',

            imageData:
              bytes,
          }),
        )

      console.log(
        'RADAR RESULT',
        result,
      )

      lastRenderedSector =
        request.sector

      lastRenderedSound =
        request.sound
    }
  }

  catch (error) {
    console.error(
      'Radar rendering failed:',
      error,
    )
  }

  finally {
    bitmapBusy =
      false

    if (
      pendingRadar
    ) {
      renderLatestRadar()
    }
  }
}

function requestRadar(
  angle: number | null,
  sound: string | null,
) {
  const sector =
    angle !== null
      ? quantizeAngle(
          angle,
        )
      : null

  const cleanSound =
    cleanSoundLabel(
      sound,
    )

  // Already displaying this state.
  if (
    !bitmapBusy &&
    !pendingRadar &&
    sector ===
      lastRenderedSector &&
    cleanSound ===
      lastRenderedSound
  ) {
    return
  }

  // Latest request replaces older pending request.
  pendingRadar = {
    sector,
    sound:
      cleanSound,
  }

  renderLatestRadar()
}

// ==================================================
// INITIAL RADAR
// ==================================================

requestRadar(
  0,
  null,
)

// ==================================================
// SOUND LATCH
// ==================================================

function updateHeldSound(
  state: any,
) {
  const now =
    Date.now()

  const incomingSound =
    typeof state.sound ===
      'string'
      ? state.sound
          .toUpperCase()
          .trim()
      : ''

  const incomingScore =
    typeof state.sound_score ===
      'number'
      ? state.sound_score
      : 0

  const incomingAngle =
    typeof state.sound_angle ===
      'number'
      ? state.sound_angle
      : typeof state.angle ===
          'number'
        ? state.angle
        : null

  // ==================================================
  // NEW SOUND EVENT
  // ==================================================

  if (
    incomingSound
  ) {
    const noHeldSound =
      !heldSound

    const heldExpired =
      now >=
      heldSoundUntil

    const sameSound =
      incomingSound ===
      heldSound

    // Don't allow a weaker random second classification
    // to instantly replace a stronger detection.
    const clearlyStronger =
      incomingScore >
      heldSoundScore +
        0.10

    if (
      noHeldSound ||
      heldExpired ||
      sameSound ||
      clearlyStronger
    ) {
      heldSound =
        incomingSound

      heldSoundScore =
        incomingScore

      if (
        incomingAngle !==
        null
      ) {
        heldSoundAngle =
          incomingAngle
      }
    }

    // Every valid sound frame refreshes the display hold.
    heldSoundUntil =
      now +
      SOUND_HOLD_MS
  }

  // ==================================================
  // EXPIRE HELD SOUND
  // ==================================================

  if (
    heldSound &&
    now >= heldSoundUntil
  ) {
    console.log(
      'Sound display expired:',
      heldSound,
    )

    heldSound = ''
    heldSoundScore = 0
    heldSoundAngle = null
  }
}

// ==================================================
// PI WEBSOCKET
// ==================================================

function connectToPi() {

  if (
    socket?.readyState ===
      WebSocket.OPEN ||
    socket?.readyState ===
      WebSocket.CONNECTING
  ) {
    return
  }

  if (
    shuttingDown
  ) {
    return
  }

  console.log(
    'Connecting to:',
    PI_WS,
  )

  socket =
    new WebSocket(
      PI_WS,
    )

  // ==================================================
  // CONNECTED
  // ==================================================

  socket.onopen = () => {

    console.log(
      'CONNECTED TO SONA PI',
    )

    setCaption(
      'Listening...',
    )

    setStatus(
      'LISTENING',
    )
  }

  // ==================================================
  // DATA
  // ==================================================

  socket.onmessage =
    event => {

      try {
        const data =
          JSON.parse(
            event.data,
          )

        if (
          data.type !==
          'frame'
        ) {
          return
        }

        const state =
          data.state

        if (
          !state
        ) {
          return
        }

        // ==================================================
        // DEBUG
        // ==================================================

        console.log(
          'SONA FRAME',
          {
            mode:
              state.mode,

            angle:
              state.angle,

            active:
              state.doa_active,

            sound:
              state.sound,

            soundAngle:
              state.sound_angle,

            score:
              state.sound_score,

            heldSound,

            heldScore:
              heldSoundScore,
          },
        )

        // ==================================================
        // MODE
        // ==================================================

        if (
          state.mode
        ) {
          setMode(
            state.mode,
          )
        }

        // ==================================================
        // LIVE PARTIAL
        // ==================================================

        if (
          typeof state.partial ===
            'string' &&
          state.partial.length > 0
        ) {
          setCaption(
            `${state.partial}...`,
          )
        }

        // ==================================================
        // FINAL CAPTION
        // ==================================================

        const history =
          state.history

        if (
          Array.isArray(
            history,
          ) &&
          history.length > 0
        ) {
          const latest =
            history[
              history.length - 1
            ]

          if (
            latest?.text &&
            latest?.shown !==
              false
          ) {
            setCaption(
              latest.text,
            )
          }
        }

        // ==================================================
        // UPDATE SOUND LATCH
        // ==================================================

        updateHeldSound(
          state,
        )

        // ==================================================
        // CHOOSE DISPLAY ANGLE
        // ==================================================

        let displayAngle:
          number | null =
            null

        // When an environmental sound is being displayed,
        // freeze the marker to that sound's direction.
        if (
          heldSound &&
          heldSoundAngle !==
            null
        ) {
          displayAngle =
            heldSoundAngle
        }

        // Otherwise show live DoA.
        else if (
          typeof state.angle ===
            'number'
        ) {
          displayAngle =
            state.angle
        }

        // ==================================================
        // DRAW
        // ==================================================

        requestRadar(
          displayAngle,
          heldSound ||
            null,
        )

        // ==================================================
        // STATUS LINE
        // ==================================================

        if (
          state.doa_active ===
            true
        ) {
          setStatus(
            'AWARENESS ACTIVE',
          )
        }

        else {
          setStatus(
            'LISTENING',
          )
        }
      }

      catch (error) {
        console.error(
          'Bad Sona frame:',
          error,
        )
      }
    }

  // ==================================================
  // ERROR
  // ==================================================

  socket.onerror =
    error => {

      console.error(
        'WebSocket error:',
        error,
      )

      setStatus(
        'PI ERROR',
      )
    }

  // ==================================================
  // CLOSED
  // ==================================================

  socket.onclose = () => {

    console.log(
      'Pi connection closed',
    )

    socket =
      null

    if (
      shuttingDown
    ) {
      return
    }

    setStatus(
      'PI DISCONNECTED',
    )

    setTimeout(
      () => {

        if (
          !socket &&
          !shuttingDown
        ) {
          connectToPi()
        }

      },

      2000,
    )
  }
}

// ==================================================
// START
// ==================================================

connectToPi()

// ==================================================
// G2 EVENTS
// ==================================================

function eventTypeOf(
  envelope?: {
    eventType?: OsEventTypeList
  },
): OsEventTypeList | null {

  if (
    !envelope
  ) {
    return null
  }

  return (
    envelope.eventType ??
    OsEventTypeList.CLICK_EVENT
  )
}

bridge.onEvenHubEvent(
  event => {

    const sysType =
      eventTypeOf(
        event.sysEvent,
      )

    const textType =
      eventTypeOf(
        event.textEvent,
      )

    // ==================================================
    // DOUBLE TAP -> EXIT
    // ==================================================

    if (
      sysType ===
        OsEventTypeList.DOUBLE_CLICK_EVENT ||
      textType ===
        OsEventTypeList.DOUBLE_CLICK_EVENT
    ) {
      cleanup()

      bridge.shutDownPageContainer(
        1,
      )

      return
    }

    // ==================================================
    // SINGLE TAP -> MODE
    // ==================================================

    if (
      sysType ===
        OsEventTypeList.CLICK_EVENT ||
      textType ===
        OsEventTypeList.CLICK_EVENT
    ) {
      let nextMode =
        'surround'

      if (
        mode ===
        'surround'
      ) {
        nextMode =
          'focus'
      }

      else if (
        mode ===
        'focus'
      ) {
        nextMode =
          'alerts'
      }

      else {
        nextMode =
          'surround'
      }

      setMode(
        nextMode,
      )

      if (
        socket?.readyState ===
        WebSocket.OPEN
      ) {
        socket.send(
          JSON.stringify({
            type: 'mode',
            value:
              nextMode,
          }),
        )
      }
    }
  },
)

// ==================================================
// CLEANUP
// ==================================================

function cleanup() {

  shuttingDown =
    true

  if (
    socket
  ) {
    socket.onclose =
      null

    socket.close()

    socket =
      null
  }
}

window.addEventListener(
  'beforeunload',
  cleanup,
)

// ==================================================
// PHONE DEBUG PAGE
// ==================================================

const app =
  document.querySelector<HTMLDivElement>(
    '#app',
  )

if (
  app
) {
  app.innerHTML = `
    <main style="
      font-family:sans-serif;
      background:#222;
      color:white;
      padding:30px;
      min-height:100vh;
    ">
      <h2>SONA G2</h2>

      <p>
        ${PI_WS}
      </p>

      <p>
        Directional awareness running.
      </p>

      <p>
        Centre of radar = held sound classification.
      </p>
    </main>
  `
}
