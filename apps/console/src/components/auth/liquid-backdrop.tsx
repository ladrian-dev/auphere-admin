"use client";

import * as React from "react";

import {
  SLOW_FRAMES_TO_STILL,
  SLOW_FRAME_MS,
  STILL_T,
  addWave,
  canvasSize,
  initialState,
  step,
  touch,
  wavesUniform,
} from "./liquid-backdrop-model";

/**
 * El líquido vivo de Entrar — spec 066, requisito 2.
 *
 * Un líquido de los verdes de Auphere que fluye solo: ruido fbm con deformación
 * de dominio en un shader pequeño (WebGL 1, un quad). El puntero lo arrastra y
 * lo ilumina por donde pasa; un clic abre una onda. Sin nadie, un «dedo
 * invisible» lo recorre y de vez en cuando abre una onda suave.
 *
 * Va a media resolución, deja de pintar cuando no se ve, se queda quieto con
 * reducir movimiento (o si la máquina no puede) y, sin WebGL, no pinta nada: el
 * respaldo CSS que hay debajo sigue ahí (R2.7). El lienzo es decoración:
 * `aria-hidden` y sin foco (R2.9).
 *
 * Escucha el puntero en el **padre** de la capa, que es el panel: la capa no
 * recibe eventos (`pointer-events: none`) y nada de la columna del formulario
 * lo alimenta.
 *
 * **El lienzo se crea en cada montaje y se tira al desmontar.** Al desmontar se
 * libera el contexto WebGL (R2.10), y un contexto liberado no vuelve: si el
 * lienzo lo pintara React, un segundo montaje (el doble montaje de desarrollo,
 * o volver a la página) heredaría un lienzo muerto y se quedaría en el respaldo.
 *
 * El mismo shader vive en la demo de la consola y en la de la app móvil.
 */

const VS = "attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}";

// Los seis verdes, de oscuro a claro: #032221 · #03624C · #2CC295 · #00DF82 ·
// un menta casi blanco y un verde azulado. El final oscurece abajo (donde va
// el titular, R3.4) y un poco arriba (donde va el logo).
const FS = `precision mediump float;
uniform vec2 R;uniform float T;uniform vec3 P;uniform vec4 W[4];
float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
 return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
float fbm(vec2 p){float v=0.,a=.5;mat2 m=mat2(1.4,1.1,-1.1,1.4);for(int i=0;i<4;i++){v+=a*n(p);p=m*p;a*=.5;}return v;}
void main(){
 vec2 uv=gl_FragCoord.xy/R;float as=R.x/R.y;vec2 p=vec2(uv.x*as,uv.y);
 vec2 pp=vec2(P.x*as,P.y);vec2 d=p-pp;float dl=dot(d,d);float inf=exp(-dl*7.)*P.z;
 p+=vec2(-d.y,d.x)*inf*.9+d*inf*.4;
 float rip=0.;
 for(int i=0;i<4;i++){vec4 w=W[i];float age=T-w.z;if(age>0.&&age<3.2){vec2 rd=p-vec2(w.x*as,w.y);float rl=length(rd);
  float ring=exp(-pow((rl-age*.5)*11.,2.))*(1.-age/3.2)*w.w;p+=rd/(rl+.001)*ring*.07;rip+=ring;}}
 float t=T*.16;vec2 b=p*.95;
 vec2 q=vec2(fbm(b+vec2(0.,t)),fbm(b+vec2(5.2,1.3)-t*.8));
 vec2 r=vec2(fbm(b+3.2*q+vec2(1.7,9.2)+t*1.4),fbm(b+3.2*q+vec2(8.3,2.8)-t*1.1));
 float f=fbm(b+3.4*r);
 vec3 c0=vec3(.012,.133,.129),c1=vec3(.012,.384,.298),c2=vec3(.173,.761,.584),c3=vec3(0.,.874,.51),c4=vec3(.78,.97,.9),c5=vec3(.09,.6,.62);
 vec3 col=mix(c0*1.2,c1*1.25,smoothstep(.18,.5,f));
 col=mix(col,c5,smoothstep(.4,.8,q.y)*.6);
 col=mix(col,c2,smoothstep(.3,.68,f*length(r)*1.3)*.9);
 col=mix(col,c3,smoothstep(.55,.9,r.x)*.45);
 col+=c4*pow(smoothstep(.6,1.,f*length(r)*1.3),3.)*.4;
 col+=c4*(inf*.28+rip*.42)+c2*inf*.28;
 col=mix(col,c0,smoothstep(.5,.04,uv.y)*.78);
 col=mix(col,c0,smoothstep(.76,1.,uv.y)*.5);
 gl_FragColor=vec4(col,1.);}`;

type GL = WebGLRenderingContext;
type Uniforms = { R: WebGLUniformLocation | null; T: WebGLUniformLocation | null; P: WebGLUniformLocation | null; W: WebGLUniformLocation | null };

/** Compila y enlaza. `null` si algo falla: el respaldo CSS se queda (R2.7). */
export function createProgram(gl: GL): Uniforms | null {
  const shader = (type: number, src: string) => {
    const s = gl.createShader(type);
    if (!s) return null;
    gl.shaderSource(s, src);
    gl.compileShader(s);
    return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null;
  };
  const v = shader(gl.VERTEX_SHADER, VS);
  const f = shader(gl.FRAGMENT_SHADER, FS);
  if (!v || !f) return null;
  const pr = gl.createProgram();
  if (!pr) return null;
  gl.attachShader(pr, v);
  gl.attachShader(pr, f);
  gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) return null;
  gl.useProgram(pr);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, "a");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  return {
    R: gl.getUniformLocation(pr, "R"),
    T: gl.getUniformLocation(pr, "T"),
    P: gl.getUniformLocation(pr, "P"),
    W: gl.getUniformLocation(pr, "W"),
  };
}

function getGL(cv: HTMLCanvasElement): GL | null {
  try {
    return cv.getContext("webgl", {
      antialias: false,
      alpha: false,
      depth: false,
      stencil: false,
      premultipliedAlpha: false,
      powerPreference: "low-power",
    }) as GL | null;
  } catch {
    return null;
  }
}

export function LiquidBackdrop({ className }: { className?: string }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [live, setLive] = React.useState(false);

  React.useEffect(() => {
    const layer = ref.current;
    const host = layer?.parentElement;
    if (!layer || !host) return;
    const cv = document.createElement("canvas");
    cv.setAttribute("aria-hidden", "true");
    cv.tabIndex = -1;
    const gl = getGL(cv);
    if (!gl) return; // R2.7: sin WebGL manda el respaldo CSS.
    const U = createProgram(gl);
    if (!U) return;
    layer.appendChild(cv);

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    const s = initialState();
    const t0 = performance.now();
    const now = () => (performance.now() - t0) / 1000;
    let raf = 0;
    let last = 0;
    let onScreen = true;
    let slow = 0;
    let tooSlow = false;
    let lost = false;
    let shown = false;

    const still = () => reduce.matches || tooSlow;
    const running = () => !lost && onScreen && !document.hidden;

    function size() {
      const r = host!.getBoundingClientRect();
      const [w, h] = canvasSize(r.width, r.height, window.devicePixelRatio || 1);
      if (cv!.width !== w || cv!.height !== h) {
        cv!.width = w;
        cv!.height = h;
        gl!.viewport(0, 0, w, h);
      }
      return [w, h] as const;
    }

    function draw(t: number) {
      const [w, h] = size();
      gl!.uniform2f(U!.R, w, h);
      gl!.uniform1f(U!.T, t);
      gl!.uniform3f(U!.P, s.ptr.x, s.ptr.y, still() ? 0.35 : s.ptr.e);
      gl!.uniform4fv(U!.W, still() ? new Float32Array(16).fill(-99) : wavesUniform(s));
      gl!.drawArrays(gl!.TRIANGLE_STRIP, 0, 4);
      if (!shown) {
        shown = true;
        setLive(true); // R2.8: el fundido sobre el respaldo, una vez pintado.
      }
    }

    function frame() {
      raf = 0;
      if (!running()) return;
      if (still()) {
        draw(STILL_T); // R2.6: un cuadro, y nada más hasta que algo cambie.
        return;
      }
      const started = performance.now();
      const t = now();
      const dt = Math.min(0.05, Math.max(0, t - last));
      last = t;
      step(s, t, dt);
      draw(t);
      // Si la máquina no puede, se queda quieto en vez de arrastrar la página.
      slow = performance.now() - started > SLOW_FRAME_MS ? slow + 1 : 0;
      if (slow >= SLOW_FRAMES_TO_STILL) {
        tooSlow = true;
        draw(STILL_T);
        return;
      }
      raf = requestAnimationFrame(frame);
    }

    function kick() {
      if (!raf && running()) raf = requestAnimationFrame(frame);
    }

    function at(ev: PointerEvent): [number, number] | null {
      const r = host!.getBoundingClientRect();
      if (!r.width || !r.height) return null;
      return [(ev.clientX - r.left) / r.width, 1 - (ev.clientY - r.top) / r.height];
    }
    function onMove(ev: PointerEvent) {
      if (still()) return;
      const p = at(ev);
      if (!p) return;
      touch(s, p[0], p[1], now());
      kick();
    }
    function onDown(ev: PointerEvent) {
      if (still()) return;
      const p = at(ev);
      if (!p) return;
      touch(s, p[0], p[1], now());
      addWave(s, p[0], p[1], now(), 1);
      kick();
    }
    function onVisibility() {
      kick();
    }
    function onReduce() {
      kick();
    }
    function onLost(ev: Event) {
      ev.preventDefault();
      lost = true;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      setLive(false); // vuelve a verse el respaldo
    }

    host.addEventListener("pointermove", onMove, { passive: true });
    host.addEventListener("pointerdown", onDown, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    reduce.addEventListener?.("change", onReduce);
    cv.addEventListener("webglcontextlost", onLost);

    // R2.5: fuera de la vista, no pinta.
    const io =
      typeof IntersectionObserver !== "undefined"
        ? new IntersectionObserver((entries) => {
            onScreen = entries.some((e) => e.isIntersecting);
            kick();
          })
        : null;
    io?.observe(host);
    // Con un cuadro quieto, un cambio de tamaño lo vuelve a pintar.
    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            if (still() && running()) draw(STILL_T);
          })
        : null;
    ro?.observe(host);

    kick();

    // R2.10: al salir de (auth) no queda nada vivo.
    return () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      host.removeEventListener("pointermove", onMove);
      host.removeEventListener("pointerdown", onDown);
      document.removeEventListener("visibilitychange", onVisibility);
      reduce.removeEventListener?.("change", onReduce);
      cv.removeEventListener("webglcontextlost", onLost);
      io?.disconnect();
      ro?.disconnect();
      gl.getExtension("WEBGL_lose_context")?.loseContext();
      cv.remove();
      setLive(false);
    };
  }, []);

  return <div ref={ref} aria-hidden="true" data-live={live ? "" : undefined} className={className ?? "auth-liquid-gl"} />;
}
