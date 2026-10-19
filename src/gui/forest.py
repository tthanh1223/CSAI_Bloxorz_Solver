"""Optional Forest Ruins. Only imported by --forest; engine stays untouched."""
from __future__ import annotations
import random
import numpy as np
import pygame
import moderngl
from src.gui.renderer3d import state_meshes, motion_meshes
from src.engine.loader import TileType


VERTEX = '''#version 330
in vec3 position; in vec3 normal; in vec3 color;
uniform mat4 camera; uniform mat4 light_camera;
out vec3 world; out vec3 n; out vec3 albedo; out vec4 light_pos;
void main(){world=position; n=normal; albedo=color;
light_pos=light_camera*vec4(position,1); gl_Position=camera*vec4(position,1);}
'''
FRAGMENT = '''#version 330
in vec3 world; in vec3 n; in vec3 albedo; in vec4 light_pos;
uniform sampler2DShadow shadow_map; uniform vec3 eye; uniform bool contrast;
out vec4 frag;
float hash(vec3 p){return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453);}
float noise(vec3 p){return .5+.22*sin(p.x*1.7+sin(p.z*2.3))+.18*sin(p.z*3.1+p.x*.8);}
void main(){
vec3 normal=normalize(n); vec3 sun=normalize(vec3(-0.6,1.0,-0.4));
vec3 lp=light_pos.xyz/light_pos.w*.5+.5;
float shade=texture(shadow_map,vec3(lp.xy,lp.z-.002));
float grain=hash(floor(world*85.));
float moss=smoothstep(.48,.75,noise(world*2.3))*max(normal.y,0.);
vec3 base=albedo*(.94+.06*grain);
if(albedo.g>albedo.r*.94 && albedo.b<albedo.r*1.15)
base=mix(base,vec3(.20,.29,.12),moss*.43);
float diffuse=max(dot(normal,sun),0.);
vec3 lit=base*(vec3(.38,.43,.33)+vec3(.95,.88,.65)*diffuse*(.23+.77*shade));
float fog=1.-exp(-max(length(eye-world)-15.,0.)*.024);
lit=mix(lit,vec3(.13,.23,.20),fog);
if(contrast)lit*=1.25;
frag=vec4(pow(lit,vec3(.85)),1.);
}
'''


def look_at(eye, target):
    eye, target = np.array(eye, dtype=float), np.array(target, dtype=float)
    forward = target-eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, (0, 1, 0)); right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    matrix = np.eye(4)
    matrix[:3, :3] = np.array([right, up, -forward])
    matrix[:3, 3] = -matrix[:3, :3] @ eye
    return matrix


def ortho(width, height, near=.1, far=120):
    return np.array([[2/width,0,0,0],[0,2/height,0,0],
                     [0,0,-2/(far-near),-(far+near)/(far-near)],[0,0,0,1.]])


def matrix_bytes(matrix):
    return np.asarray(matrix.T, dtype='f4').tobytes()


class ForestRenderer:
    """Real depth-tested geometry, directional shadow map and procedural stone.

    A standalone GL framebuffer is read into Pygame so all existing controls work.
    Static frames are cached to avoid GPU readback when the scene is unchanged.
    """
    def __init__(self):
        self.ctx = moderngl.create_standalone_context(require=330)
        self.program = self.ctx.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
        self.depth_program = self.ctx.program(vertex_shader='''#version 330
in vec3 position; uniform mat4 light_camera;
void main(){gl_Position=light_camera*vec4(position,1);}''', fragment_shader='''#version 330
void main(){}''')
        self.shadow = self.ctx.depth_texture((1024,1024))
        self.shadow.repeat_x = self.shadow.repeat_y = False
        self.shadow.compare_func = '<='
        self.shadow_fbo = self.ctx.framebuffer(depth_attachment=self.shadow)
        self.fbo = None
        self.zoom, self.pan, self.high_contrast = 1., (0,0), False
        self.stage = None
        self.cache_key = None
        self.static = []

    @staticmethod
    def mesh(data, vertices, color):
        vertices = np.asarray(vertices, dtype=float)
        for face in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            a,b,c = vertices[list(face[:3])]
            normal = np.cross(c-a,b-a); normal /= max(np.linalg.norm(normal),1e-9)
            for i in (0,1,2,0,2,3):
                data.extend((*vertices[face[i]], *normal, *color))

    def box(self, data, x,y,z, sx,sy,sz, color):
        vertices=[(x,y,z),(x+sx,y,z),(x+sx,y,z+sz),(x,y,z+sz),
                  (x,y+sy,z),(x+sx,y+sy,z),(x+sx,y+sy,z+sz),(x,y+sy,z+sz)]
        self.mesh(data,vertices,color)

    def set_stage(self, stage):
        self.stage=stage
        self.bridges={cell:i for i,cells in enumerate(stage.bridges.values()) for cell in cells}
        cells=[(r,c) for r,row in enumerate(stage.grid) for c,t in enumerate(row) if t!=TileType.VOID]
        self.center=np.array([(min(c for r,c in cells)+max(c for r,c in cells)+1)/2,
                              0.,(min(r for r,c in cells)+max(r for r,c in cells)+1)/2])
        self.span=max(max(c for r,c in cells)-min(c for r,c in cells)+2,
                      max(r for r,c in cells)-min(r for r,c in cells)+2,8)
        rng=random.Random(41)
        self.static=[]
        cx,_,cz=self.center
        self.box(self.static,cx-40,-1.5,cz-40,80,.4,80,(.16,.23,.16))
        # Ruined colonnades and distant trunks frame, rather than cover, the board.
        for side in (-1,1):
            for i in range(7):
                x=cx+side*(self.span*.72+1+rng.random()*4)
                z=cz-self.span*.65+i*2.4
                h=rng.uniform(2.5,7)
                stone=(.39,.43,.32)
                self.box(self.static,x-.45,-1.1,z-.45,.9,.4,.9,stone)
                for j in range(int(h/.65)):
                    self.box(self.static,x-.24,-.7+j*.65,z-.24,.48,.62,.48,stone)
                self.box(self.static,x-.43,h-.9,z-.43,.86,.24,.86,stone)
            for i in range(12):
                x=cx+side*rng.uniform(self.span*.8,self.span*2.2)
                z=cz-rng.uniform(self.span*.8,self.span*2.2)
                h=rng.uniform(8,15)
                self.box(self.static,x,-1.1,z,.32,h,.38,(.14,.20,.14))
                for j in range(3):
                    self.box(self.static,x-2+j*.4,h-3+j,z-1.5,4-j*.8,.7,3,(.12,.23,.13))
        for i in range(95):
            x=cx+rng.uniform(-self.span*1.7,self.span*1.7)
            z=cz+rng.uniform(-self.span*1.7,self.span*1.7)
            self.box(self.static,x,-1.1,z,.2,rng.uniform(.12,.5),.25,(.24,.34,.15))
        if hasattr(self,'static_vbo'):
            self.static_vao.release(); self.static_depth_vao.release(); self.static_vbo.release()
        self.static_vbo=self.ctx.buffer(np.asarray(self.static,dtype='f4').tobytes())
        self.static_vao=self.ctx.vertex_array(self.program,[(self.static_vbo,'3f 3f 3f','position','normal','color')])
        self.static_depth_vao=self.ctx.vertex_array(self.depth_program,[(self.static_vbo,'3f 24x','position')])
        self.cache_key=None

    def draw(self, surface, state, motion=None):
        size=surface.get_size()
        key=(size,state,motion,self.zoom,tuple(self.pan),self.high_contrast)
        if key==self.cache_key:
            surface.blit(self.cached,(0,0)); return
        # Render the scene below UI resolution to keep the preview affordable on iGPUs.
        render_size=tuple(max(1,round(d*.65)) for d in size)
        if self.fbo is None or self.fbo.size!=render_size:
            if self.fbo is not None:
                self.fbo.release(); self.color_buffer.release(); self.depth_buffer.release()
            self.color_buffer=self.ctx.renderbuffer(render_size)
            self.depth_buffer=self.ctx.depth_renderbuffer(render_size)
            self.fbo=self.ctx.framebuffer([self.color_buffer],self.depth_buffer)
        data=[]
        shown=motion.before if motion and motion.progress<.65 else state
        for r,row in enumerate(self.stage.grid):
            for c,tile in enumerate(row):
                bridge=self.bridges.get((r,c))
                if bridge is not None:
                    if bridge>=len(shown.bridges_status) or not shown.bridges_status[bridge]: continue
                elif tile==TileType.VOID: continue
                color=(.53,.57,.43) if bridge is None else (.35,.48,.39)
                if tile==TileType.FRAGILE: color=(.57,.39,.25)
                if (r,c)==self.stage.goal:
                    # Actual opening: four rim stones and a recessed dark floor.
                    for dx,dz,sx,sz in ((0,0,1,.14),(0,.86,1,.14),(0,.14,.14,.72),(.86,.14,.14,.72)):
                        self.box(data,c+dx,-.33,r+dz,sx,.33,sz,color)
                    self.box(data,c+.14,-.8,r+.14,.72,.05,.72,(.035,.07,.05))
                else:
                    self.box(data,c+.025,-.36,r+.025,.95,.33,.95,color)
                    self.box(data,c+.055,-.03,r+.055,.89,.03,.89,tuple(v*1.12 for v in color))
                if (r,c) in self.stage.switches:
                    kind=self.stage.switches[(r,c)].type.value
                    ink=(.85,.69,.33)
                    strokes={'SOFT':[(.25,.25,.5,.06),(.25,.69,.5,.06),(.25,.25,.06,.5),(.69,.25,.06,.5)],
                             'HEAVY':[(.22,.46,.56,.08),(.46,.22,.08,.56)],
                             'SPLIT':[(.25,.25,.12,.5),(.63,.25,.12,.5)]}[kind]
                    for x,z,sx,sz in strokes:self.box(data,c+x,.008,r+z,sx,.015,sz,ink)
        for vertices,active in motion_meshes(motion) if motion else state_meshes(state):
            # Convert the engine's (row,col,height) convention into GL (x,y,z).
            mapped=[(c,z,r) for r,c,z in vertices]
            self.mesh(data,mapped,(.95,.66,.25) if active else (.72,.43,.17))
        vbo=self.ctx.buffer(np.asarray(data,dtype='f4').tobytes())
        vao=self.ctx.vertex_array(self.program,[(vbo,'3f 3f 3f','position','normal','color')])
        depth_vao=self.ctx.vertex_array(self.depth_program,[(vbo,'3f 24x','position')])
        target=self.center+np.array([0,.2,0])
        eye=target+np.array([18,21,18])
        view=look_at(eye,target)
        height=self.span*1.02/self.zoom
        projection=ortho(height*size[0]/size[1],height)
        projection[0,3]+=2*self.pan[0]/size[0]
        projection[1,3]-=2*self.pan[1]/size[1]
        light=ortho(self.span*3,self.span*3) @ look_at(target+np.array([-24,40,-16]),target)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.shadow_fbo.use(); self.ctx.viewport=(0,0,1024,1024); self.shadow_fbo.clear(depth=1)
        self.depth_program['light_camera'].write(matrix_bytes(light))
        self.static_depth_vao.render(); depth_vao.render()
        self.fbo.use(); self.ctx.viewport=(0,0,*render_size); self.fbo.clear(.10,.18,.15,1,depth=1)
        self.program['camera'].write(matrix_bytes(projection@view))
        self.program['light_camera'].write(matrix_bytes(light))
        self.program['eye'].value=tuple(eye)
        self.program['contrast'].value=self.high_contrast
        self.shadow.use(0); self.program['shadow_map'].value=0
        self.static_vao.render(); vao.render()
        raw=pygame.image.frombytes(self.fbo.read(components=3,alignment=1),render_size,'RGB',True)
        self.cached=pygame.transform.smoothscale(raw,size)
        surface.blit(self.cached,(0,0)); self.cache_key=key
        depth_vao.release(); vao.release(); vbo.release()

    def close(self):
        self.ctx.release()


def enable_forest(app):
    from src.gui import theme
    from src.gui import ui
    # This changes tokens only in the explicitly selected Forest process.
    colors={'BG':(19,31,26),'PANEL':(25,39,31),'SURFACE':(36,51,39),
            'HOVER':(48,65,46),'PRESSED':(59,73,47),'LINE':(53,68,49),
            'TEXT':(235,232,210),'MUTED':(165,180,150),'ACCENT':(221,185,104)}
    for name,color in colors.items():
        setattr(theme,name,color)
        if hasattr(ui,name):setattr(ui,name,color)
    renderer=ForestRenderer()
    renderer.set_stage(app.stage)
    app.renderer=renderer
    app.visual_style='forest_gl'
    app.message='FOREST RUINS  /  Arrows or WASD to roll. Right-drag to pan; wheel to zoom.'
