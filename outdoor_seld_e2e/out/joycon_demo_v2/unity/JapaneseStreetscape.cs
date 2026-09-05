// Procedural Japanese streets. Layout coordinates remain the source of truth.
// Visual detail only: no audio, label, detection, or notification data is changed.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;

public sealed partial class JapaneseStreetscape : MonoBehaviour
{
    public string SceneType { get; private set; } = "residential";
    public float WalkDirection { get; private set; }
    public float WalkSpeed { get; private set; }
    public float TrainHeight { get; private set; }
    public bool MapMode { get; private set; }
    public int BuildingCount { get; private set; }
    public int RoadCount { get { return roads.Count; } }
    public int TriangleCount { get; private set; }
    public string LayoutPath { get; private set; }
    public const float Extent = 115f;
    const float PavementHeight = .12f;
    struct Road { public Vector3 a, b; public float width; public bool foot, rail; public float height; }
    struct Lane { public float at, dir, height; public string kind; }
    readonly List<Road> roads = new List<Road>();
    readonly List<Mesh> ownedMeshes = new List<Mesh>();
    readonly Dictionary<string, Batch> batches = new Dictionary<string, Batch>();
    readonly List<Vector4> lots = new List<Vector4>();
    readonly List<Vector4> buildingBounds = new List<Vector4>();
    GameObject decorations;
    System.Random random;
    static readonly Dictionary<string, Material> materials = new Dictionary<string, Material>();
    static readonly Dictionary<PrimitiveType, Mesh> primitives = new Dictionary<PrimitiveType, Mesh>();
    static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
    static readonly Color[] Walls = { new Color(.73f,.70f,.63f), new Color(.84f,.81f,.73f), new Color(.58f,.59f,.57f), new Color(.81f,.79f,.73f), new Color(.48f,.44f,.40f), new Color(.68f,.67f,.62f) };
    sealed class Batch
    {
        public Material material; public bool decoration;
        public readonly List<Vector3> vertices = new List<Vector3>();
        public readonly List<Vector3> normals = new List<Vector3>();
        public readonly List<Vector2> uv = new List<Vector2>();
        public readonly List<int> indices = new List<int>();
    }

    public static JapaneseStreetscape Build(string path, Transform parent = null)
    {
        var root = new GameObject("Japanese streetscape");
        if (parent != null) root.transform.SetParent(parent, false);
        var result = root.AddComponent<JapaneseStreetscape>();
        result.Generate(path);
        return result;
    }
    static float F(string[] p, int i, float fallback = 0)
    { float f; return i < p.Length && float.TryParse(p[i], NumberStyles.Float, Inv, out f) ? f : fallback; }
    static Vector3 Map(float x, float y) { return new Vector3(-y, 0, x); }
    float R(float a, float b) { return Mathf.Lerp(a, b, (float)random.NextDouble()); }
    int RI(int count) { return random.Next(count); }
    static int Seed(string[] lines)
    {
        // File names differ between oracle/model versions; identical layouts must look identical.
        unchecked { int h = 713; foreach (string line in lines) foreach (char c in line.Trim()) h = h * 31 + c; return h; }
    }
    void Generate(string path)
    {
        LayoutPath = path;
        string[] lines = File.Exists(path) ? File.ReadAllLines(path) : new string[0];
        random = new System.Random(Seed(lines));
        decorations = new GameObject("Buildings vegetation and street furniture (V)");
        decorations.transform.SetParent(transform, false);
        var lanes = new List<Lane>(); var cross = new List<Lane>(); var pois = new List<string[]>(); var buildings = new List<string[]>();
        foreach (string line in lines)
        {
            string[] p = line.Trim().Split(','); if (p.Length < 2) continue;
            switch (p[0])
            {
                case "scene": SceneType = p[1]; WalkDirection = p.Length > 2 && p[2] == "walk" ? F(p,3) : 0; WalkSpeed = F(p,4); break;
                case "map": MapMode = true; break;
                case "lane": lanes.Add(new Lane { at = -F(p,1), dir = F(p,2), kind = p.Length > 3 ? p[3] : "car" }); break;
                case "xlane": cross.Add(new Lane { at = F(p,1), dir = F(p,2), kind = p.Length > 3 ? p[3] : "car", height = F(p,4) }); break;
                case "static": case "poi": pois.Add(p); break;
                case "bldg": buildings.Add(p); break;
            }
        }
        PlanObserverRoute(lanes);
        Box("earth", new Vector3(0,-.15f,0), new Vector3(420,.24f,420), false);
        if (MapMode)
        {
            foreach (string line in lines)
            {
                var p = line.Trim().Split(',');
                if (p.Length < 6 || (p[0] != "road" && p[0] != "rail" && p[0] != "water")) continue;
                Vector3 a = Map(F(p,1),F(p,2)), b = Map(F(p,3),F(p,4));
                if (Distance(Vector3.zero,a,b) > 175) continue;
                if (p[0] == "water") { Strip("water",a,b,Mathf.Max(3,F(p,5)),.002f,false); continue; }
                string kind = p.Length > 6 ? p[6] : "road";
                bool foot = kind == "footway" || kind == "path" || kind == "pedestrian" || kind == "steps" || kind == "cycleway";
                roads.Add(new Road { a=a,b=b,width=Mathf.Clamp(F(p,5,5),foot?1.2f:2.5f,18),foot=foot,rail=p[0]=="rail" });
            }
        }
        else
        {
            AddLaneRoads(lanes,false); AddLaneRoads(cross,true);
            if (roads.FindAll(r=>!r.rail).Count == 0)
                roads.Add(new Road { a=new Vector3(WalkRight+2.46f,0,-Extent),b=new Vector3(WalkRight+2.46f,0,Extent),width=4.8f });
        }
        if(!MapMode && SceneType != "parking") NeighborhoodRoads();
        if(!MapMode && !roads.Exists(r=>r.rail))
            foreach(var p in pois) if(p.Length>3 && p[0]=="static" && p[3]=="crossing")
            { float z=F(p,1); roads.Add(new Road{a=new Vector3(-Extent,0,z),b=new Vector3(Extent,0,z),width=3.4f,rail=true}); break; }
        foreach (Road road in roads) if(SceneType != "parking" || road.rail || MapMode) DrawRoad(road);
        if (!MapMode && SceneType == "parking") Parking();
        if (MapMode)
        {
            foreach (var p in buildings)
            {
                Vector3 c = Map(F(p,1),F(p,2)); if(c.magnitude>155) continue;
                float w=Mathf.Max(2,F(p,4)),d=Mathf.Max(2,F(p,3)),h=Mathf.Clamp(F(p,6,6),3,32);
                House(c,w,d,h,-F(p,5),h<9 && w<14 && d<14,true);
            }
            MapPlanting();
        }
        else if (SceneType != "parking") Neighborhood();
        foreach (var p in pois)
        {
            if(p.Length<4) continue; Vector3 at=Map(F(p,1),F(p,2)); if(at.magnitude>145) continue;
            if(p[3]=="crossing" && p[0]=="static") RailwayCrossing(at);
            else if(p[3]=="crossing") CrosswalkAt(at);
            else if(p[3]=="signal") Signal(at,Quaternion.identity);
            else if(p[3]=="gate") Gate(at);
            else if(p[3]=="bus_stop") BusStop(at,Quaternion.identity);
        }
        if(!MapMode && path.Contains("バス"))
        { Road rr=roads.Find(r=>!r.rail&&!r.foot); Vector3 mid=(rr.a+rr.b)*.5f; BusStop(mid+Vector3.left*(rr.width*.5f+1.0f),Quaternion.identity); }
        DrawObserverRoute();
        Flush();
    }
    void AddLaneRoads(List<Lane> input, bool horizontal)
    {
        var cars = new List<Lane>();
        foreach(var l in input)
            if(l.kind=="train")
            {
                TrainHeight=Mathf.Max(TrainHeight,l.height);
                roads.Add(new Road { a=horizontal?new Vector3(-Extent,0,l.at):new Vector3(l.at,0,-Extent), b=horizontal?new Vector3(Extent,0,l.at):new Vector3(l.at,0,Extent), width=3.4f,rail=true,height=l.height });
            }
            else cars.Add(l);
        cars.Sort((a,b)=>a.at.CompareTo(b.at));
        // Nearby trajectory centres share one carriageway. Large gaps remain separate streets.
        for(int i=0;i<cars.Count;)
        {
            float min=cars[i].at,max=min; int j=i+1;
            while(j<cars.Count && cars[j].at-max<7.1f && (horizontal || Mathf.Sign(cars[j].at)==Mathf.Sign(min))) { max=cars[j].at; j++; }
            float margin=SceneType=="residential"?1.65f:1.8f;
            float width=Mathf.Max(SceneType=="residential"?4.2f:5.0f,max-min+margin*2);
            float c=(min+max)*.5f;
            if(!horizontal)
            {
                float lo=c-width*.5f,hi=c+width*.5f;
                if(c<0){hi=Mathf.Min(hi,WalkLeft-.06f);lo=Mathf.Min(lo,hi-3.0f);}
                else {lo=Mathf.Max(lo,WalkRight+.06f);hi=Mathf.Max(hi,lo+3.0f);}
                width=hi-lo;c=(lo+hi)*.5f;
            }
            roads.Add(new Road {a=horizontal?new Vector3(-Extent,0,c):new Vector3(c,0,-Extent),b=horizontal?new Vector3(Extent,0,c):new Vector3(c,0,Extent),width=width});
            i=j;
        }
    }
    void NeighborhoodRoads()
    {
        var longitudinal=roads.FindAll(r=>!r.rail&&!r.foot&&Mathf.Abs((r.b-r.a).normalized.z)>.8f);
        if(longitudinal.Count==0)return;
        if(longitudinal.Count>2)return;
        float min=999,max=-999;
        foreach(var r in longitudinal){min=Mathf.Min(min,r.a.x-r.width*.5f);max=Mathf.Max(max,r.a.x+r.width*.5f);}
        int side=RI(2)==0?-1:1;float outer=side<0?min-R(30,38):max+R(30,38);
        Road main=side<0?longitudinal[0]:longitudinal[longitudinal.Count-1];
        roads.Add(new Road{a=new Vector3(outer,0,-Extent),b=new Vector3(outer,0,Extent),width=4.3f});
        foreach(float z in new[]{R(33,46),R(-61,-43)})
            roads.Add(new Road{a=new Vector3(Mathf.Min(main.a.x,outer),0,z),b=new Vector3(Mathf.Max(main.a.x,outer),0,z),width=4.2f});
    }
    static float Distance(Vector3 p,Vector3 a,Vector3 b)
    { Vector3 d=b-a; return Vector3.Distance(p,a+d*Mathf.Clamp01(Vector3.Dot(p-a,d)/Mathf.Max(.001f,d.sqrMagnitude))); }
    bool Blocked(Vector3 p,float radius)
    {
        // Keep the full recorded observer route clear, including waiting corners.
        if(InObserverCorridor(p,radius+.4f))return true;
        foreach(var r in roads)
            if(r.height<2 && Distance(p,r.a,r.b)<r.width*.5f+radius+(r.foot?.3f:1.5f)) return true;
        return false;
    }
    bool Junction(Vector3 p, Road current, float padding=0)
    {
        foreach(var r in roads)
        {
            if(r.height>2 || r.foot || r.a==current.a && r.b==current.b) continue;
            // Collinear map segments should not erase each other's markings.
            if(Mathf.Abs(Vector3.Dot((r.b-r.a).normalized,(current.b-current.a).normalized))>.96f) continue;
            if(Distance(p,r.a,r.b)<r.width*.5f+padding) return true;
        }
        return false;
    }
    void DrawRoad(Road r)
    {
        if(r.rail) { Railway(r); return; }
        Vector3 dir=(r.b-r.a).normalized,right=Vector3.Cross(Vector3.up,dir); float len=Vector3.Distance(r.a,r.b);
        if(len<.1f) return;
        Quaternion rot=Quaternion.LookRotation(dir);
        if(r.foot)
        {
            for(float s=.5f;s<len;s+=1)
            {
                Vector3 p=r.a+dir*s;
                if(!Junction(p,r,.5f))Box("pavers",p+Vector3.up*.07f,new Vector3(r.width,.14f,1.01f),false,rot);
            }
        }
        else RoadSurface(r);
        // Round caps close angled map segments without a stack of square road ends.
        if(MapMode) foreach(Vector3 at in new[]{r.a,r.b}) if(!InObserverCorridor(at,r.width*.5f)) Cylinder(r.foot?"pavers":"asphalt",at+Vector3.up*(r.foot?.07f:-.014f),new Vector3(r.width,.04f,r.width),false);
        if(r.foot) return;
        bool urban=SceneType=="arterial" || SceneType=="daily" || MapMode;
        for(float s=1;s<len-1;s+=1.5f)
        {
            Vector3 p=r.a+dir*s;
            for(int side=-1;side<=1;side+=2)
            {
                Vector3 edge=p+right*side*(r.width*.5f);
                if(Junction(edge,r,1.2f) || OnObserverSide(edge)) continue;
                if(urban)
                {
                    Box("pavers",edge+right*side*.88f+Vector3.up*.047f,new Vector3(1.75f,.145f,1.51f),false,rot);
                    Box("curb",edge+right*side*.08f+Vector3.up*.08f,new Vector3(.16f,.20f,1.46f),false,rot);
                }
                else Box("concrete",edge+right*side*.21f+Vector3.up*.011f,new Vector3(.42f,.045f,1.47f),false,rot);
                if(((int)(s/1.5f))%9==0)
                {
                    Box("iron",edge-right*side*.14f+Vector3.up*.025f,new Vector3(.28f,.014f,.65f),false,rot);
                    for(int k=0;k<6;k++) Box("curb",edge-right*side*.14f+dir*(k*.09f-.24f)+Vector3.up*.035f,new Vector3(.23f,.018f,.025f),false,rot);
                }
            }
            if(!Junction(p,r,2) && !InObserverCorridor(p,r.width*.5f))
            {
                if(urban && r.width>6.2f && ((int)(s/1.5f))%4<2)
                    Box("paint",p+Vector3.up*.029f,new Vector3(.13f,.012f,1.48f),false,rot);
                if(r.width>4.5f) for(int side=-1;side<=1;side+=2)
                    Box("paint",p+right*side*(r.width*.5f-.38f)+Vector3.up*.026f,new Vector3(.10f,.01f,1.49f),false,rot);
            }
        }
        for(float s=8;s<len-6;s+=R(18,28))
        {
            Vector3 p=r.a+dir*s+right*R(-r.width*.3f,r.width*.3f);
            if(InObserverCorridor(p,.7f))continue;
            Cylinder("iron",p+Vector3.up*.026f,new Vector3(.58f,.016f,.58f),false);
            // Resurfaced utility trenches with restrained contrast and broken crack branches.
            if(!Junction(p,r,1))
            {
                Box("patch",p+dir*2+Vector3.up*.027f,new Vector3(R(.6f,1.4f),.009f,R(1.7f,3.6f)),false,rot);
                for(int k=0;k<3;k++) Strip("crack",p+dir*(k*.4f),p+dir*((k+1)*.4f)+right*R(-.23f,.23f),.018f,.034f,false);
            }
        }
        // Street furniture is staggered, with intersection openings and separate utility spans.
        Vector3? previous=null;
        for(float s=R(3,14);s<len-4;s+=R(23,32))
        {
            Vector3 p=r.a+dir*s+right*(r.width*.5f+(urban?1.5f:.85f));
            if(Junction(p,r,3)) { previous=null; continue; }
            UtilityPole(p,rot);
            if(previous.HasValue && Vector3.Distance(previous.Value,p)<40)
                for(int k=-1;k<=1;k++) Wire(previous.Value+right*k*.42f+Vector3.up*8.0f,p+right*k*.42f+Vector3.up*8.0f);
            previous=p;
            if(urban) Lamp(p-right*(r.width+2.8f),rot);
        }
        if(!MapMode)
            foreach(var other in roads)
            {
                if(other.rail || other.foot || Mathf.Abs(Vector3.Dot((other.b-other.a).normalized,dir))>.5f) continue;
                Vector3 centre=(other.a+other.b)*.5f; Vector3 p=r.a+dir*Vector3.Dot(centre-r.a,dir);
                if(Distance(p,other.a,other.b)>other.width*.5f) continue;
                for(int side=-1;side<=1;side+=2)
                    Zebra(p+dir*side*(other.width*.5f+2.1f),r.width,rot);
            }
    }
    void Zebra(Vector3 p,float width,Quaternion rot)
    {
        for(float x=-width*.5f+.55f;x<width*.5f-.4f;x+=.85f)
            Box("paint",p+rot*new Vector3(x,.036f,0),new Vector3(.43f,.018f,2.7f),false,rot);
        for(int s=-1;s<=1;s+=2)
            Box("tactile",p+rot*new Vector3(s*(width*.5f+.6f),.13f,0),new Vector3(.65f,.025f,1.6f),false,rot);
    }
    void CrosswalkAt(Vector3 p)
    {
        Road nearest=default; float best=999;
        foreach(var r in roads) if(!r.foot&&!r.rail) { float d=Distance(p,r.a,r.b); if(d<best){best=d;nearest=r;} }
        if(best>12) return; Vector3 dir=(nearest.b-nearest.a).normalized;
        Vector3 centre=nearest.a+dir*Mathf.Clamp(Vector3.Dot(p-nearest.a,dir),0,Vector3.Distance(nearest.a,nearest.b));
        Zebra(centre,nearest.width,Quaternion.LookRotation(dir));
    }
    void Neighborhood()
    {
        foreach(var road in roads)
        {
            if(road.rail||road.foot) continue;
            Vector3 dir=(road.b-road.a).normalized,right=Vector3.Cross(Vector3.up,dir);
            float len=Vector3.Distance(road.a,road.b); float angle=Quaternion.LookRotation(dir).eulerAngles.y;
            for(int side=-1;side<=1;side+=2)
            {
                for(float s=R(3,10);s<len-8;)
                {
                    bool commercial=SceneType!="residential" && RI(5)<2;
                    float frontage=R(commercial?9:7,commercial?17:11),depth=R(7,12);
                    float setback=R(2.1f,5.2f),along=s+frontage*.5f;
                    Vector3 centre=road.a+dir*along+right*side*(road.width*.5f+1.8f+setback+depth*.5f);
                    float w=depth,d=frontage-.9f,h=commercial?R(9,17):RI(5)==0?3.5f:R(5.5f,6.8f);
                    float radius=Mathf.Sqrt(w*w+d*d)*.5f;
                    bool occupied=false; foreach(var lot in lots) if(Vector2.Distance(new Vector2(centre.x,centre.z),new Vector2(lot.x,lot.y))<(lot.z+radius)*.83f){occupied=true;break;}
                    if(!occupied && !Blocked(centre,radius-.9f))
                    {
                        lots.Add(new Vector4(centre.x,centre.z,radius,0));
                        Box("gravel",centre,new Vector3(w+setback*2,.025f,d+.65f),true,Quaternion.Euler(0,angle,0));
                        Vector3 driveway=centre-right*side*(depth*.5f+setback*.45f);
                        Box("concrete",driveway+Vector3.up*.022f,new Vector3(setback+1.1f,.045f,d*.65f),true,Quaternion.Euler(0,angle,0));
                        House(centre,w,d,h,angle+R(-2.2f,2.2f),!commercial && RI(7)!=0,false);
                        Vector3 frontagePoint=centre-right*side*(depth*.5f+setback-.15f);
                        Vector3 boundary=centre+dir*(frontage*.5f);
                        Box("block",boundary+Vector3.up*.45f,new Vector3(depth+setback*1.5f,.9f,.16f),true,Quaternion.Euler(0,angle,0));
                        Box("block",frontagePoint+dir*d*.33f+Vector3.up*.4f,new Vector3(.17f,.8f,d*.30f),true,Quaternion.Euler(0,angle,0));
                        Box("mail",frontagePoint+dir*d*.30f+Vector3.up*1.03f,new Vector3(.25f,.22f,.38f),true,Quaternion.Euler(0,angle,0));
                        if(RI(3)!=0) Tree(centre+right*side*(depth*.5f+.9f)+dir*(d*.3f),R(2.6f,4.7f));
                        if(RI(3)==0 && setback>3) ParkedCar(driveway,Quaternion.Euler(0,angle+side*90,0),RI(4));
                        if(commercial) Shop(frontagePoint,Quaternion.Euler(0,angle-side*90,0),d);
                        else Hedge(frontagePoint-dir*d*.34f,Quaternion.Euler(0,angle,0),d*.28f);
                    }
                    s+=frontage+R(.5f,2.4f);
                }
            }
        }
    }
    void House(Vector3 centre,float w,float d,float h,float angle,bool pitched,bool surveyed)
    {
        Quaternion rot=Quaternion.Euler(0,angle,0); string wall="wall"+RI(Walls.Length);
        Action<string,Vector3,Vector3> b=(mat,p,size)=>Box(mat,centre+rot*p,size,true,rot);
        b("foundation",new Vector3(0,.23f,0),new Vector3(w+.14f,.46f,d+.14f));
        b(wall,new Vector3(0,h*.5f+.25f,0),new Vector3(w,h,d));
        int floors=Mathf.Max(1,Mathf.RoundToInt(h/3)); float floorH=h/floors;
        string roof=RI(3)==0?"roofBrown":"roof";
        if(pitched)
        {
            float rise=Mathf.Min(w*.25f,2.3f),top=h+.3f,half=w*.5f+.32f,ends=d*.5f+.34f;
            bool hip=RI(3)==0;float inset=hip?Mathf.Min(ends*.5f,half*.8f):0;
            Vector3 a=new Vector3(-half,top,-ends),b0=new Vector3(-half,top,ends),c=new Vector3(0,top+rise,ends-inset),e=new Vector3(0,top+rise,-ends+inset),f=new Vector3(half,top,-ends),g=new Vector3(half,top,ends);
            Quad(roof,centre,rot,a,b0,c,e,true); Quad(roof,centre,rot,e,c,g,f,true);
            if(hip)
            {
                Triangle(roof,centre+rot*a,centre+rot*e,centre+rot*f,true);
                Triangle(roof,centre+rot*g,centre+rot*c,centre+rot*b0,true);
            }
            else
            {
                Triangle(wall,centre+rot*new Vector3(-w/2,top,-d/2),centre+rot*new Vector3(0,top+rise,-d/2),centre+rot*new Vector3(w/2,top,-d/2),true);
                Triangle(wall,centre+rot*new Vector3(w/2,top,d/2),centre+rot*new Vector3(0,top+rise,d/2),centre+rot*new Vector3(-w/2,top,d/2),true);
            }
            b("ridge",new Vector3(0,top+rise+.045f,0),new Vector3(.18f,.13f,d+.8f-inset*2));
            for(int side=-1;side<=1;side+=2)
            {
                b("ridge",new Vector3(side*(w*.5f+.25f),top-.03f,0),new Vector3(.13f,.12f,d+.8f));
                b("ridge",new Vector3(side*(w*.5f+.10f),h*.5f,d*.42f),new Vector3(.075f,h,.075f));
            }
            // Thin standing seams break up roofs without exaggerating tile scale.
            for(float z=-d*.5f+inset;z<d*.5f-inset;z+=.56f)
                for(int side=-1;side<=1;side+=2)
                    Beam("ridge",centre+rot*new Vector3(0,top+rise+.018f,z),centre+rot*new Vector3(side*half,top+.018f,z),.025f,true);
            if(!hip && RI(4)==0)
                Box("solar",centre+rot*new Vector3(w*.23f,top+rise*.55f+.07f,0),new Vector3(w*.35f,.035f,d*.58f),true,rot*Quaternion.Euler(0,0,-Mathf.Atan2(rise,half)*Mathf.Rad2Deg));
        }
        else
        {
            b("roof",new Vector3(0,h+.30f,0),new Vector3(w+.28f,.18f,d+.28f));
            for(int s=-1;s<=1;s+=2)
            {
                b(wall,new Vector3(s*w*.5f,h+.48f,0),new Vector3(.15f,.4f,d));
                b(wall,new Vector3(0,h+.48f,s*d*.5f),new Vector3(w,.4f,.15f));
            }
            b("equipment",new Vector3(w*.24f,h+.64f,d*.20f),new Vector3(1.3f,.65f,.9f));
        }
        for(int side=-1;side<=1;side+=2)
        {
            for(int floor=0;floor<floors;floor++)
            {
                float y=.25f+floor*floorH+floorH*.58f;
                for(float z=-d*.5f+1.35f;z<d*.5f-.65f;z+=2.3f)
                {
                    float ww=Mathf.Min(1.4f,d*.22f),hh=Mathf.Min(1.25f,floorH*.48f);
                    b("frame",new Vector3(side*(w*.5f+.028f),y,z),new Vector3(.075f,hh+.16f,ww+.17f));
                    b("glass",new Vector3(side*(w*.5f+.072f),y,z),new Vector3(.025f,hh,ww));
                    b("frame",new Vector3(side*(w*.5f+.095f),y,z),new Vector3(.028f,hh,.035f));
                    b("curb",new Vector3(side*(w*.5f+.16f),y-hh*.5f-.1f,z),new Vector3(.32f,.08f,ww+.25f));
                    if(floor==floors-1 && RI(4)==0)
                    {
                        b("equipment",new Vector3(side*(w*.5f+.26f),y-hh*.5f-.52f,z),new Vector3(.48f,.48f,.74f));
                        b("iron",new Vector3(side*(w*.5f+.51f),y-hh*.5f-.52f,z),new Vector3(.018f,.30f,.51f));
                    }
                }
                for(float x=-w*.5f+1.2f;x<w*.5f-.6f;x+=2.35f)
                {
                    b("frame",new Vector3(x,y,side*(d*.5f+.028f)),new Vector3(1.3f,1.25f,.075f));
                    b("glass",new Vector3(x,y,side*(d*.5f+.073f)),new Vector3(1.12f,1.08f,.025f));
                    b("frame",new Vector3(x,y,side*(d*.5f+.095f)),new Vector3(.04f,1.1f,.025f));
                }
            }
            b("door",new Vector3(side*(w*.5f+.045f),1.30f,-d*.25f),new Vector3(.11f,2.1f,.92f));
            b("roof",new Vector3(side*(w*.5f+.45f),2.48f,-d*.25f),new Vector3(1.0f,.11f,1.6f));
            b("concrete",new Vector3(side*(w*.5f+.5f),.12f,-d*.25f),new Vector3(1.0f,.24f,1.5f));
            if(floors==2 && !surveyed && RI(3)!=0)
            {
                float y=floorH+.3f;
                b("curb",new Vector3(side*(w*.5f+.48f),y,0),new Vector3(.95f,.16f,d*.46f));
                b("frame",new Vector3(side*(w*.5f+.92f),y+.85f,0),new Vector3(.065f,.065f,d*.46f));
                for(float z=-d*.23f;z<d*.23f;z+=.35f)
                    b("frame",new Vector3(side*(w*.5f+.92f),y+.45f,z),new Vector3(.035f,.85f,.035f));
            }
        }
        BuildingCount++;
        buildingBounds.Add(new Vector4(centre.x,centre.z,Mathf.Sqrt(w*w+d*d)*.5f,0));
    }
    void Shop(Vector3 p,Quaternion rot,float width)
    {
        Box("awning",p+rot*new Vector3(0,2.8f,-1.0f),new Vector3(width*.68f,.13f,1.2f),true,rot*Quaternion.Euler(-8,0,0));
        Box("sign",p+rot*new Vector3(0,3.3f,-1.35f),new Vector3(width*.60f,.7f,.12f),true,rot);
        Box("vending",p+rot*new Vector3(width*.32f,.95f,0),new Vector3(.92f,1.9f,.75f),true,rot);
        Box("glass",p+rot*new Vector3(width*.32f,1.18f,.39f),new Vector3(.74f,.83f,.02f),true,rot);
        for(int i=0;i<3;i++) Box("paint",p+rot*new Vector3(width*.32f,.98f+i*.23f,.41f),new Vector3(.66f,.045f,.025f),true,rot);
    }
    void Tree(Vector3 p,float h)
    {
        if(InObserverCorridor(p,.45f))return;
        Cylinder("bark",p+Vector3.up*h*.38f,new Vector3(.22f,h*.38f,.23f),true);
        for(int i=0;i<6;i++)
        {
            float a=i*2.4f; Vector3 at=p+new Vector3(Mathf.Cos(a)*h*.18f,h*.67f+R(-.2f,.6f),Mathf.Sin(a)*h*.18f);
            Primitive("leaf"+(i%3),PrimitiveType.Sphere,at,new Vector3(h*.52f,h*.48f,h*.50f),Quaternion.Euler(R(-15,15),i*63,R(-15,15)),true);
        }
    }
    void Hedge(Vector3 p,Quaternion rot,float length)
    {
        Box("soil",p+Vector3.up*.08f,new Vector3(.8f,.16f,length),true,rot);
        for(float z=-length*.5f;z<length*.5f;z+=.6f)
            Primitive("leaf1",PrimitiveType.Sphere,p+rot*new Vector3(0,.65f,z),new Vector3(.8f,1.0f,.85f),rot,true);
    }
    void MapPlanting()
    {
        // Fill only unoccupied land; surveyed building rectangles are retained exactly.
        for(int i=0;i<160;i++)
        {
            Vector3 p=new Vector3(R(-120,120),0,R(-120,120)); if(Blocked(p,3))continue;
            bool inBuilding=false;
            foreach(var bounds in buildingBounds)
                if(Vector2.Distance(new Vector2(p.x,p.z),new Vector2(bounds.x,bounds.y))<bounds.z+3){inBuilding=true;break;}
            if(!inBuilding)Tree(p,R(3.6f,6.3f));
        }
    }
    void UtilityPole(Vector3 p,Quaternion rot)
    {
        if(InObserverCorridor(p,.45f))return;
        Cylinder("pole",p+Vector3.up*4.3f,new Vector3(.24f,4.3f,.24f),true);
        Box("iron",p+Vector3.up*8,new Vector3(1.8f,.10f,.10f),true,rot);
        for(int k=-1;k<=1;k++) Cylinder("ceramic",p+rot*new Vector3(k*.6f,8.15f,0),new Vector3(.12f,.15f,.12f),true);
        Cylinder("equipment",p+rot*new Vector3(.35f,6.7f,0),new Vector3(.43f,.44f,.43f),true);
        Box("yellow",p+rot*new Vector3(0,1.2f,-.125f),new Vector3(.2f,.75f,.026f),true,rot);
        for(int k=0;k<3;k++) Box("iron",p+rot*new Vector3(0,.97f+k*.23f,-.146f),new Vector3(.20f,.09f,.016f),true,rot*Quaternion.Euler(0,0,-25));
    }
    void Wire(Vector3 a,Vector3 b)
    {
        Vector3 prev=a;
        for(int k=1;k<=10;k++) {float t=k/10f; Vector3 next=Vector3.Lerp(a,b,t)-Vector3.up*(Mathf.Sin(t*Mathf.PI)*.65f); Beam("wire",prev,next,.022f,true);prev=next;}
    }
    void Lamp(Vector3 p,Quaternion rot)
    {
        if(InObserverCorridor(p,.45f))return;
        Cylinder("iron",p+Vector3.up*3.1f,new Vector3(.095f,3.1f,.095f),true);
        Box("iron",p+rot*new Vector3(.4f,6.15f,0),new Vector3(.85f,.09f,.09f),true,rot);
        Box("lamp",p+rot*new Vector3(.8f,6.12f,0),new Vector3(.5f,.12f,.24f),true,rot);
    }
    void Signal(Vector3 p,Quaternion rot)
    {
        if(InObserverCorridor(p,.45f))return;
        Cylinder("pole",p+Vector3.up*2.7f,new Vector3(.14f,2.7f,.14f),true);
        Box("iron",p+rot*new Vector3(.9f,5.2f,0),new Vector3(1.8f,.12f,.12f),true,rot);
        Box("equipment",p+rot*new Vector3(1.5f,5.0f,0),new Vector3(1.05f,.40f,.32f),true,rot);
        for(int k=0;k<3;k++) Primitive(k==0?"signalGreen":"iron",PrimitiveType.Sphere,p+rot*new Vector3(1.16f+k*.33f,5,-.18f),new Vector3(.23f,.23f,.055f),rot,true);
    }
    void Gate(Vector3 p)
    {
        if(InObserverCorridor(p,.45f))return;
        for(int s=-1;s<=1;s+=2) { Box("block",p+new Vector3(s*1.9f,.9f,0),new Vector3(.55f,1.8f,.6f),true);Box("curb",p+new Vector3(s*1.9f,1.84f,0),new Vector3(.7f,.1f,.75f),true); }
        Box("sign",p+new Vector3(-1.9f,1.12f,-.31f),new Vector3(.40f,.65f,.02f),true);
    }
    void BusStop(Vector3 p,Quaternion rot)
    {
        if(InObserverCorridor(p,.45f))return;
        for(int s=-1;s<=1;s+=2) Box("iron",p+rot*new Vector3(0,1.25f,s*1.8f),new Vector3(.09f,2.5f,.09f),true,rot);
        Box("roof",p+Vector3.up*2.55f,new Vector3(1.65f,.11f,4.3f),true,rot);
        Box("wood",p+Vector3.up*.5f,new Vector3(.52f,.1f,2.6f),true,rot);
        for(int s=-1;s<=1;s+=2) Box("iron",p+rot*new Vector3(0,.25f,s),new Vector3(.42f,.5f,.08f),true,rot);
        Vector3 pole=p+rot*new Vector3(-.5f,0,2.5f);
        Cylinder("pole",pole+Vector3.up*1.1f,new Vector3(.065f,1.1f,.065f),true);
        Box("sign",pole+Vector3.up*1.85f,new Vector3(.42f,.55f,.055f),true,rot);
    }
    void Parking()
    {
        Box("asphalt",new Vector3(0,.007f,0),new Vector3(39,.04f,155),false);
        for(int side=-1;side<=1;side+=2)
        {
            for(float z=-70;z<72;z+=2.65f)
            {
                Box("paint",new Vector3(side*11,.037f,z),new Vector3(5.2f,.01f,.09f),false);
                Box("concrete",new Vector3(side*13,.13f,z+1.30f),new Vector3(.20f,.22f,1.35f),false);
                if(RI(5)<3) ParkedCar(new Vector3(side*11,.025f,z+1.32f),Quaternion.Euler(0,-side*90,0),RI(4));
            }
            Fence(new Vector3(side*19,0,-76),new Vector3(side*19,0,76));
            for(float z=-60;z<=60;z+=30) Lamp(new Vector3(side*18,0,z),Quaternion.identity);
        }
        for(float z=-63;z<70;z+=21)
        {Box("paint",new Vector3(4,.04f,z),new Vector3(.13f,.015f,2),false);Box("paint",new Vector3(4.33f,.04f,z+.7f),new Vector3(.13f,.015f,.85f),false,Quaternion.Euler(0,-45,0));}
        House(new Vector3(-26,0,28),9,14,5.4f,0,false,false);
        for(int i=0;i<7;i++)Tree(new Vector3(22,0,-65+i*20),R(3,5));
    }
    void ParkedCar(Vector3 p,Quaternion rot,int variant)
    {
        string mat=variant==0?"carWhite":variant==1?"carSilver":variant==2?"carBlue":"carDark";
        Box("rubber",p+Vector3.up*.4f,new Vector3(1.58f,.40f,3.9f),true,rot);
        Box(mat,p+Vector3.up*.66f,new Vector3(1.72f,.53f,4.1f),true,rot);
        Box("glass",p+rot*new Vector3(0,1.14f,-.1f),new Vector3(1.49f,.66f,2.14f),true,rot);
        Box(mat,p+rot*new Vector3(0,1.49f,-.15f),new Vector3(1.53f,.095f,2.0f),true,rot);
        for(int side=-1;side<=1;side+=2)
        {
            for(int end=-1;end<=1;end+=2)
            {
                Primitive("rubber",PrimitiveType.Cylinder,p+rot*new Vector3(side*.85f,.34f,end*1.25f),new Vector3(.58f,.13f,.58f),rot*Quaternion.Euler(0,0,90),true);
                Primitive("equipment",PrimitiveType.Cylinder,p+rot*new Vector3(side*.99f,.34f,end*1.25f),new Vector3(.33f,.025f,.33f),rot*Quaternion.Euler(0,0,90),true);
                Box(end==1?"lamp":"red",p+rot*new Vector3(side*.55f,.72f,end*2.06f),new Vector3(.38f,.16f,.025f),true,rot);
            }
            Box(mat,p+rot*new Vector3(side*.77f,1.13f,0),new Vector3(.055f,.69f,.12f),true,rot);
        }
    }
    void Railway(Road r)
    {
        Vector3 dir=(r.b-r.a).normalized,right=Vector3.Cross(Vector3.up,dir);Quaternion rot=Quaternion.LookRotation(dir);float len=Vector3.Distance(r.a,r.b),y=r.height;
        if(y>2)
        {
            Strip("concrete",r.a,r.b,4.8f,y-.75f,false,.75f);
            for(int s=-1;s<=1;s+=2) Strip("concrete",r.a+right*s*2.35f,r.b+right*s*2.35f,.18f,y+.5f,false,1.0f);
            for(float t=6;t<len;t+=16)
            {
                Vector3 p=r.a+dir*t; if(Blocked(p,1.8f)) continue;
                Box("concrete",p+Vector3.up*(y-.75f)*.5f,new Vector3(1.35f,y-.75f,1.5f),false,rot);
                Box("concrete",p+Vector3.up*(y-1.0f),new Vector3(4.4f,.65f,1.8f),false,rot);
            }
        }
        Strip("gravel",r.a,r.b,3.5f,y+.03f,false,.16f);
        for(float s=.4f;s<len;s+=.65f)
        {
            Vector3 p=r.a+dir*s;
            if(y<2 && Junction(p,r,.3f))Box("rubber",p+Vector3.up*.21f,new Vector3(3.45f,.12f,.66f),false,rot);
            else Box("sleeper",p+Vector3.up*(y+.16f),new Vector3(2.05f,.13f,.22f),false,rot);
        }
        for(int side=-1;side<=1;side+=2)
        {
            Strip("iron",r.a+right*side*.535f,r.b+right*side*.535f,.065f,y+.25f,false,.13f);
            if(y<2)
                for(float s=0;s<len-1;s+=2.7f)
                {
                    Vector3 a=r.a+dir*s+right*side*2.3f,b=a+dir*2.7f;
                    if(!Junction(a,r,1.8f)&&!Junction(b,r,1.8f))Fence(a,b);
                }
        }
        for(float s=8;s<len;s+=28)
        {
            Vector3 p=r.a+dir*s+Vector3.up*y;
            for(int side=-1;side<=1;side+=2) Box("pole",p+right*side*2.55f+Vector3.up*3.2f,new Vector3(.14f,6.4f,.14f),true,rot);
            Box("iron",p+Vector3.up*6.4f,new Vector3(5.3f,.13f,.13f),true,rot);
        }
        Beam("wire",r.a+Vector3.up*(y+5.9f),r.b+Vector3.up*(y+5.9f),.025f,true);
    }
    void RailwayCrossing(Vector3 p)
    {
        // Use an explicit train track when supplied; otherwise place the warning installation only.
        for(int side=-1;side<=1;side+=2)
        {
            Vector3 at=p+new Vector3(side*2.2f,0,0);
            if(InObserverCorridor(at,.25f))continue;
            Box("yellow",at+Vector3.up*1.8f,new Vector3(.14f,3.6f,.14f),false);
            for(int k=0;k<9;k++)Box("iron",at+Vector3.up*(.2f+k*.4f),new Vector3(.15f,.18f,.15f),false);
            for(int k=-1;k<=1;k+=2)Box("yellow",at+Vector3.up*3.45f,new Vector3(1.05f,.12f,.06f),false,Quaternion.Euler(0,0,k*45));
            Box("iron",at+new Vector3(0,2.8f,0),new Vector3(.65f,.3f,.22f),false);
            for(int k=-1;k<=1;k+=2) Primitive("red",PrimitiveType.Sphere,at+new Vector3(k*.19f,2.8f,-.13f),new Vector3(.17f,.17f,.06f),Quaternion.identity,false);
            Box("equipment",at+new Vector3(.25f,.45f,0),new Vector3(.55f,.9f,.65f),false);
            // Raised arm: its decorative state is not a simulated safety signal.
            for(int k=0;k<10;k++)Box(k%2==0?"yellow":"iron",at+new Vector3(.4f,1.1f+k*.3f,0),new Vector3(.07f,.30f,.07f),false);
        }
    }
    void Fence(Vector3 a,Vector3 b)
    {
        Vector3 dir=(b-a).normalized; float len=Vector3.Distance(a,b);
        for(float s=0;s<=len;s+=2.7f)Box("iron",a+dir*s+Vector3.up*.66f,new Vector3(.045f,1.32f,.045f),true);
        for(int k=0;k<4;k++)Beam("iron",a+Vector3.up*(.25f+k*.31f),b+Vector3.up*(.25f+k*.31f),.022f,true);
    }

    // Shared, low contrast materials. Texture UVs are measured in metres, not stretched per road.
    static Material Mat(string key)
    {
        Material mat; if(materials.TryGetValue(key,out mat)&&mat!=null)return mat;
        Color c=new Color(.5f,.5f,.48f); int texture=0; float gloss=.05f;
        if(key.StartsWith("wall"))c=Walls[int.Parse(key.Substring(4),Inv)%Walls.Length];
        else switch(key)
        {
            case "shoulder":c=new Color(.46f,.47f,.42f);texture=1;break;
            case "asphalt":c=new Color(.23f,.245f,.25f);texture=1;break;
            case "patch":c=new Color(.21f,.225f,.23f);texture=1;break;
            case "crack":c=new Color(.115f,.12f,.12f);break;
            case "earth":c=new Color(.39f,.41f,.32f);texture=1;break;
            case "soil":c=new Color(.32f,.28f,.22f);texture=1;break;
            case "pavers":c=new Color(.62f,.61f,.56f);texture=2;break;
            case "curb":case "concrete":c=new Color(.65f,.65f,.61f);texture=1;break;
            case "block":case "foundation":c=new Color(.49f,.50f,.47f);texture=3;break;
            case "gravel":c=new Color(.43f,.42f,.37f);texture=4;break;
            case "paint":c=new Color(.85f,.83f,.73f);texture=1;break;
            case "roof":case "ridge":c=new Color(.20f,.24f,.26f);texture=1;break;
            case "roofBrown":c=new Color(.32f,.23f,.19f);texture=1;break;
            case "glass":c=new Color(.17f,.28f,.32f);gloss=.65f;break;
            case "solar":c=new Color(.12f,.20f,.29f);gloss=.6f;texture=3;break;
            case "frame":c=new Color(.27f,.29f,.28f);gloss=.35f;break;
            case "equipment":case "carSilver":c=new Color(.68f,.70f,.68f);gloss=.4f;break;
            case "iron":case "wire":c=new Color(.18f,.20f,.20f);gloss=.25f;break;
            case "rubber":c=new Color(.08f,.09f,.09f);break;
            case "pole":c=new Color(.47f,.49f,.48f);texture=1;break;
            case "bark":case "wood":case "door":c=new Color(.31f,.25f,.19f);texture=1;break;
            case "leaf0":c=new Color(.24f,.34f,.17f);texture=1;break;
            case "leaf1":c=new Color(.31f,.40f,.21f);texture=1;break;
            case "leaf2":c=new Color(.37f,.43f,.24f);texture=1;break;
            case "tactile":case "yellow":c=new Color(.83f,.65f,.21f);texture=key=="tactile"?4:0;break;
            case "red":c=new Color(.65f,.12f,.09f);break;
            case "carWhite":case "ceramic":c=new Color(.83f,.84f,.79f);gloss=.35f;break;
            case "carBlue":c=new Color(.21f,.32f,.42f);gloss=.45f;break;
            case "carDark":c=new Color(.18f,.20f,.22f);gloss=.45f;break;
            case "lamp":c=new Color(.91f,.90f,.73f);break;
            case "sign":case "mail":case "awning":c=new Color(.22f,.36f,.36f);break;
            case "vending":c=new Color(.72f,.22f,.18f);break;
            case "signalGreen":c=new Color(.18f,.66f,.52f);break;
            case "water":c=new Color(.25f,.39f,.40f);gloss=.7f;texture=1;break;
            case "sleeper":c=new Color(.36f,.33f,.27f);texture=1;break;
        }
        mat=new Material(Shader.Find("Standard")) { name="Streets / "+key,color=c };
        mat.SetFloat("_Glossiness",gloss);
        if(texture>0)mat.mainTexture=Texture(texture);
        materials[key]=mat;return mat;
    }
    static readonly Dictionary<int,Texture2D> textures=new Dictionary<int,Texture2D>();
    static Texture2D Texture(int kind)
    {
        Texture2D tex;if(textures.TryGetValue(kind,out tex)&&tex!=null)return tex;
        const int size=256; var pixels=new Color32[size*size];var rng=new System.Random(1257+kind);
        for(int y=0;y<size;y++)for(int x=0;x<size;x++)
        {
            float v=.92f+(float)rng.NextDouble()*.15f;
            if(kind==2 && (y%64<2 || (x+(y/64%2)*64)%128<2))v*=.65f;
            if(kind==3 && (y%64<2 || (x+(y/64%2)*64)%128<2))v*=.78f;
            if(kind==4)v=.78f+Mathf.PerlinNoise(x*.24f,y*.24f)*.43f;
            byte b=(byte)Mathf.Clamp(v*240,0,255);pixels[y*size+x]=new Color32(b,b,b,255);
        }
        tex=new Texture2D(size,size,TextureFormat.RGB24,true){name="Street surface "+kind,wrapMode=TextureWrapMode.Repeat,anisoLevel=8};
        tex.SetPixels32(pixels);tex.Apply(true,true);textures[kind]=tex;return tex;
    }
    Batch GetBatch(string key,bool decoration)
    {
        string id=(decoration?"D/":"R/")+key;Batch b;
        if(!batches.TryGetValue(id,out b)){b=new Batch{material=Mat(key),decoration=decoration};batches.Add(id,b);}return b;
    }
    void Triangle(string mat,Vector3 a,Vector3 b,Vector3 c,bool deco)
    {
        Batch batch=GetBatch(mat,deco); Vector3 n=Vector3.Cross(b-a,c-a).normalized;int start=batch.vertices.Count;
        foreach(Vector3 v in new[]{a,b,c})
        {
            batch.vertices.Add(v);batch.normals.Add(n);
            batch.uv.Add(Mathf.Abs(n.y)>.5f?new Vector2(v.x,v.z):Mathf.Abs(n.x)>.5f?new Vector2(v.z,v.y):new Vector2(v.x,v.y));
        }
        batch.indices.Add(start);batch.indices.Add(start+1);batch.indices.Add(start+2);
    }
    void Quad(string mat,Vector3 p,Quaternion q,Vector3 a,Vector3 b,Vector3 c,Vector3 d,bool deco)
    {a=p+q*a;b=p+q*b;c=p+q*c;d=p+q*d;Triangle(mat,a,b,c,deco);Triangle(mat,a,c,d,deco);}
    void Box(string mat,Vector3 p,Vector3 size,bool deco,Quaternion rot=default)
    {
        if(rot==default)rot=Quaternion.identity; Vector3 h=size*.5f;
        Vector3 a=new Vector3(-h.x,-h.y,-h.z),b=new Vector3(-h.x,-h.y,h.z),c=new Vector3(h.x,-h.y,h.z),d=new Vector3(h.x,-h.y,-h.z);
        Vector3 e=a+Vector3.up*size.y,f=b+Vector3.up*size.y,g=c+Vector3.up*size.y,j=d+Vector3.up*size.y;
        Quad(mat,p,rot,e,f,g,j,deco);Quad(mat,p,rot,a,d,c,b,deco);Quad(mat,p,rot,a,b,f,e,deco);Quad(mat,p,rot,d,j,g,c,deco);Quad(mat,p,rot,a,e,j,d,deco);Quad(mat,p,rot,b,c,g,f,deco);
    }
    void Strip(string mat,Vector3 a,Vector3 b,float width,float y,bool deco,float thick=.025f)
    {Vector3 delta=b-a; if(delta.sqrMagnitude<.001f)return;Box(mat,(a+b)*.5f+Vector3.up*y,new Vector3(width,thick,delta.magnitude),deco,Quaternion.LookRotation(delta));}
    void Beam(string mat,Vector3 a,Vector3 b,float width,bool deco)
    {Vector3 d=b-a;if(d.sqrMagnitude>.00001f)Box(mat,(a+b)*.5f,new Vector3(width,width,d.magnitude),deco,Quaternion.LookRotation(d));}
    void Cylinder(string mat,Vector3 p,Vector3 scale,bool deco)
    {Primitive(mat,PrimitiveType.Cylinder,p,scale,Quaternion.identity,deco);}
    void Primitive(string mat,PrimitiveType type,Vector3 p,Vector3 scale,Quaternion q,bool deco)
    {
        Mesh mesh;if(!primitives.TryGetValue(type,out mesh)||mesh==null)
        {
            GameObject source=GameObject.CreatePrimitive(type);source.SetActive(false);mesh=source.GetComponent<MeshFilter>().sharedMesh;primitives[type]=mesh;
            if(Application.isPlaying)Destroy(source);else DestroyImmediate(source);
        }
        Batch batch=GetBatch(mat,deco);int start=batch.vertices.Count;Vector3[] verts=mesh.vertices,normals=mesh.normals;Vector2[] uv=mesh.uv;
        for(int i=0;i<verts.Length;i++){batch.vertices.Add(p+q*Vector3.Scale(verts[i],scale));batch.normals.Add((q*new Vector3(normals[i].x/scale.x,normals[i].y/scale.y,normals[i].z/scale.z)).normalized);batch.uv.Add(uv[i]*2);}
        foreach(int index in mesh.triangles)batch.indices.Add(start+index);
    }
    void Flush()
    {
        foreach(var pair in batches)
        {
            Batch b=pair.Value;if(b.vertices.Count==0)continue;
            Mesh mesh=new Mesh{name=pair.Key,indexFormat=IndexFormat.UInt32};mesh.SetVertices(b.vertices);mesh.SetNormals(b.normals);mesh.SetUVs(0,b.uv);mesh.SetTriangles(b.indices,0);mesh.RecalculateBounds();ownedMeshes.Add(mesh);TriangleCount+=b.indices.Count/3;
            GameObject go=new GameObject(pair.Key);go.transform.SetParent(b.decoration?decorations.transform:transform,false);go.AddComponent<MeshFilter>().sharedMesh=mesh;
            var renderer=go.AddComponent<MeshRenderer>();renderer.sharedMaterial=b.material;renderer.shadowCastingMode=ShadowCastingMode.On;renderer.receiveShadows=true;
        }
        batches.Clear();
    }
    public void SetDecorations(bool visible){if(decorations!=null)decorations.SetActive(visible);}
    void OnDestroy(){foreach(var mesh in ownedMeshes)if(mesh!=null){if(Application.isPlaying)Destroy(mesh);else DestroyImmediate(mesh);}}

    public static void ConfigureLighting()
    {
        RenderSettings.ambientMode=AmbientMode.Trilight;
        RenderSettings.ambientSkyColor=new Color(.67f,.73f,.80f);
        RenderSettings.ambientEquatorColor=new Color(.53f,.56f,.57f);
        RenderSettings.ambientGroundColor=new Color(.36f,.36f,.32f);
        RenderSettings.fog=true;RenderSettings.fogMode=FogMode.Linear;RenderSettings.fogColor=new Color(.73f,.78f,.80f);RenderSettings.fogStartDistance=100;RenderSettings.fogEndDistance=240;
        QualitySettings.shadowDistance=95;QualitySettings.shadows=ShadowQuality.All;QualitySettings.shadowResolution=ShadowResolution.High;QualitySettings.antiAliasing=4;
        Light sun=null;foreach(var light in UnityEngine.Object.FindObjectsByType<Light>())if(light.type==LightType.Directional){sun=light;break;}
        if(sun==null)sun=new GameObject("Daylight").AddComponent<Light>();
        sun.type=LightType.Directional;sun.transform.rotation=Quaternion.Euler(48,-32,0);sun.color=new Color(1,.96f,.87f);sun.intensity=1.05f;sun.shadows=LightShadows.Soft;sun.shadowStrength=.65f;sun.shadowBias=.035f;RenderSettings.sun=sun;
    }
}
