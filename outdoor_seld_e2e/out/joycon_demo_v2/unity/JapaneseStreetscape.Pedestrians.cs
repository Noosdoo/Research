using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

public sealed partial class JapaneseStreetscape
{
    public float WalkLeft { get; private set; } = -.9f;
    public float WalkRight { get; private set; } = .9f;
    public bool RaisedWalkway { get; private set; } = true;
    public const float ObserverRadius = .22f;
    float routeStart=-Extent,routeEnd=Extent;

    void PlanObserverRoute(List<Lane> lanes)
    {
        float leftLimit=-99,rightLimit=99;
        foreach(var lane in lanes)
        {
            if(lane.kind=="train")continue;
            float halfWidth=LaneVehicleHalfWidth(lane.at);
            if(lane.at<0)leftLimit=Mathf.Max(leftLimit,lane.at+halfWidth+.04f);
            else rightLimit=Mathf.Min(rightLimit,lane.at-halfWidth-.04f);
        }
        WalkLeft=Mathf.Clamp(leftLimit,-.9f,-.3f);
        WalkRight=Mathf.Clamp(rightLimit,.3f,.9f);
        float missing=1.8f-(WalkRight-WalkLeft);
        if(missing>0)
        {
            float extra=Mathf.Min(missing,Mathf.Max(0,rightLimit-WalkRight));WalkRight+=extra;missing-=extra;
            WalkLeft-=Mathf.Min(missing,Mathf.Max(0,WalkLeft-leftLimit));
        }
        RaisedWalkway=leftLimit<=-.26f && rightLimit>=.26f;
        if(MapMode)
        {
            WalkLeft=-.7f;WalkRight=.7f;RaisedWalkway=true;
            routeStart=WalkDirection==0?-2.5f:Mathf.Min(-WalkDirection*WalkSpeed*5,WalkDirection*WalkSpeed*5)-2;
            routeEnd=WalkDirection==0?1.0f:Mathf.Max(-WalkDirection*WalkSpeed*5,WalkDirection*WalkSpeed*5)+2;
        }
    }
    float LaneVehicleHalfWidth(float laneX)
    {
        string path=LayoutPath.Replace("_layout.csv","_scene.csv");
        if(!File.Exists(path))return .9f;
        float best=999,result=.9f;
        foreach(string line in File.ReadLines(path))
        {
            var p=line.Split(',');if(p.Length<5)continue;
            float t=F(p,0,-1);if(t<4.8f||t>5.2f)continue;
            float x=-F(p,4)*Mathf.Sin(F(p,3)*Mathf.Deg2Rad);
            float diff=Mathf.Abs(x-laneX);if(diff>=best)continue;best=diff;
            result=p[2]=="bike"?.34f:p[2]=="bike_bell"?.28f:p[2]=="kick"?.25f:p[2]=="siren"?1.0f:p[2]=="backup_beep"?1.15f:.9f;
        }
        return result;
    }
    bool InObserverCorridor(Vector3 p,float padding=0)
    { return p.x>WalkLeft-padding && p.x<WalkRight+padding && p.z>routeStart-padding && p.z<routeEnd+padding; }
    bool ObserverCrossing(Vector3 p)
    {
        if(MapMode && WalkDirection==0 && p.z<1.2f)return false;
        foreach(var road in roads)
        {
            if(road.foot || road.height>2)continue;
            var dir=(road.b-road.a).normalized;
            if(Mathf.Abs(dir.x)<.45f)continue;
            if(Distance(p,road.a,road.b)<road.width*.5f+.08f)return true;
        }
        return false;
    }
    public string ObserverSurface(float z)
    {
        if(z<routeStart||z>routeEnd)return "outside route";
        if(ObserverCrossing(new Vector3(0,0,z)))return "crossing";
        return SceneType=="parking" || !RaisedWalkway ? "marked shoulder" : "sidewalk";
    }
    public float ObserverGroundHeight(float z)
    {return ObserverCrossing(new Vector3(0,0,z))?.045f:RaisedWalkway && SceneType!="parking"?.14f:.045f;}
    bool OnObserverSide(Vector3 edge)
    {return InObserverCorridor(edge,.12f);}
    void DrawObserverRoute()
    {
        // This is a surface under the recorded observer, never a relocated observer.
        float width=WalkRight-WalkLeft,centre=(WalkLeft+WalkRight)*.5f;
        for(float z=routeStart+.25f;z<routeEnd;z+=.5f)
        {
            var p=new Vector3(centre,0,z);bool crossing=ObserverCrossing(new Vector3(0,0,z));
            if(crossing)
            {
                if(((int)Mathf.Floor(z/.5f))%2==0)
                    Box("paint",p+Vector3.up*.046f,new Vector3(Mathf.Max(2.2f,width),.015f,.42f),false);
            }
            else
            {
                bool raised=RaisedWalkway && SceneType!="parking";
                Box(raised?"pavers":"shoulder",p+Vector3.up*(raised?.075f:.025f),new Vector3(width,raised?.13f:.025f,.505f),false);
                for(int side=-1;side<=1;side+=2)
                {
                    float x=side<0?WalkLeft:WalkRight;
                    if(raised)Box("curb",new Vector3(x,.075f,z),new Vector3(.10f,.15f,.495f),false);
                    else Box("paint",new Vector3(x,.049f,z),new Vector3(.08f,.012f,.49f),false);
                }
            }
        }
        // Tactile warning tiles and flush ramps at both ends of each actual crossing.
        bool previous=ObserverCrossing(new Vector3(0,0,routeStart));
        for(float z=routeStart+.25f;z<routeEnd;z+=.25f)
        {
            bool current=ObserverCrossing(new Vector3(0,0,z));
            if(current!=previous)
            {
                float side=current?-1:1;
                Box("tactile",new Vector3(centre,.151f,z+side*.45f),new Vector3(width-.18f,.015f,.55f),false);
            }
            previous=current;
        }
    }
    void RoadSurface(Road r)
    {
        // Map road widths are schematic. Trim only the visual surface around the retained
        // walking/waiting forecourt; keep road centrelines, building footprints and data intact.
        if(!MapMode){Strip("asphalt",r.a,r.b,r.width,.005f,false);return;}
        Vector3 dir=(r.b-r.a).normalized,right=Vector3.Cross(Vector3.up,dir);float len=Vector3.Distance(r.a,r.b);
        Quaternion rot=Quaternion.LookRotation(dir);
        for(float s=.35f;s<len;s+=.7f)
        {
            Vector3 p=r.a+dir*s;
            if(!InObserverCorridor(p,r.width*.5f+1) || ObserverCrossing(new Vector3(0,0,p.z)))
            {Box("asphalt",p,new Vector3(r.width,.025f,Mathf.Min(.72f,len-s+.35f)),false,rot);continue;}
            for(float x=-r.width*.5f+.12f;x<r.width*.5f;x+=.24f)
            {
                Vector3 at=p+right*x;if(InObserverCorridor(at,.06f))continue;
                Box("asphalt",at,new Vector3(.245f,.025f,.72f),false,rot);
            }
        }
    }
}
