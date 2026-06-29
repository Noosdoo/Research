% ===== 既存2ツールはどちらも「部屋」：同じ車(233472)で示す＋試聴 =====
% 必要ファイル（同フォルダ）:
%   irs.mat（room IR）/ car_dry.wav, car_metu.wav, car_seldgen.wav（同一の車を各部屋へ）
% 自作（自由音場）は次回ゼミの内容なので扱わない。

thisdir = fileparts(mfilename('fullpath'));
if isempty(thisdir), thisdir = fileparts(matlab.desktop.editor.getActiveFilename); end
S = load(fullfile(thisdir,'irs.mat'));
cR=[0.82 0.29 0.36]; cB=[0.23 0.49 0.65]; cK=[0.4 0.4 0.4];

[E1,t1,T1] = edc_t60(S.ir_ss, double(S.sr_ss));   % SpatialScaper 実測室(metu)
[E2,t2,T2] = edc_t60(S.ir_sg, double(S.sr_sg));   % SELD-Data-Generator シミュ室(pra)

% ===== 図1：EDC（残響時間 T60）=====
figure('Color',[0.15 0.15 0.15]); hold on;
plot(t1,E1,'LineWidth',2,'Color',cR); plot(t2,E2,'LineWidth',2,'Color',cB);
yline(-60,'--','Color',[.7 .7 .7]); xlim([0 1.5]); ylim([-80 2]); grid on;
lg=legend({sprintf('SpatialScaper 実測室  T60\\approx%.1f s',T1), ...
           sprintf('SELD-Data-Generator シミュ室  T60\\approx%.2f s',T2)},'Location','northeast');
lg.TextColor='w'; lg.Color=[0.2 0.2 0.2];
xlabel('time [s]'); ylabel('Energy Decay Curve [dB]');
title('既存ツールの空間化はどちらも「部屋」（T60>0）');
ax=gca; ax.XColor='w'; ax.YColor='w'; ax.Color=[0.15 0.15 0.15]; ax.GridColor=[.5 .5 .5];

% ===== 図2：同じ車(233472)・鳴り止み後の残響尾 =====
dry=audioread(fullfile(thisdir,'car_dry.wav'));
met=audioread(fullfile(thisdir,'car_metu.wav'));
sld=audioread(fullfile(thisdir,'car_seldgen.wav'));
fs=24000; tcut=2.5;     % 車の鳴り止む瞬間
figure('Color',[0.15 0.15 0.15]);
tail_panel(1,dry,fs,cK,tcut,'元音源（室内残響なし）');
tail_panel(2,met,fs,cR,tcut,sprintf('SpatialScaper 実測室'));
tail_panel(3,sld,fs,cB,tcut,sprintf('SELD-Data-Generator シミュ室'));
xlabel('time [s]   （点線=車が鳴り止む瞬間。以降の尾＝部屋の残響）','Color','w');
% sgtitle('同じ車を各ツールの部屋に通す：鳴り止み後に残響の尾（既存=部屋）','Color','w');

fprintf('T60  SpatialScaper(metu)=%.2fs  SELDGEN(shoebox)=%.2fs\n',T1,T2);

% ===== 試聴（同じ車233472。聞きたい行の % を外す）=====
% [y,fs]=audioread(fullfile(thisdir,'car_dry.wav'));      soundsc(y,fs)  % 乾き（残響なし）
% [y,fs]=audioread(fullfile(thisdir,'car_metu.wav'));     soundsc(y,fs)  % 実測室（ホール残響）
% [y,fs]=audioread(fullfile(thisdir,'car_seldgen.wav'));  soundsc(y,fs)  % シミュ室（小部屋残響）

% ---------- ローカル関数 ----------
function [EDC,t,T60] = edc_t60(h, fs)
    h=double(h(:)); h=h/(max(abs(h))+1e-12);
    E=flipud(cumsum(flipud(h.^2))); EDC=10*log10(E/max(E)+1e-12);
    t=(0:numel(h)-1)'/fs;
    i1=find(EDC<=-5,1); i2=find(EDC<=-25,1);   % T20法（実測IRはノイズ床でT30が過大になるため）
    if isempty(i2)||i2<=i1, T60=NaN; else, p=polyfit(t(i1:i2),EDC(i1:i2),1); T60=-60/p(1); end
end
function tail_panel(k,y,fs,c,tcut,ti)
    t=(0:numel(y)-1)'/fs;
    subplot(3,1,k); plot(t,y,'Color',c,'LineWidth',0.6); hold on;
    xline(tcut,':','Color','w','LineWidth',1);
    xlim([tcut-0.3 tcut+1.5]); ylim([-1 1]); grid on;
    title(ti,'Color','w'); ylabel('amp');
    ax=gca; ax.XColor='w'; ax.YColor='w'; ax.Color=[0.15 0.15 0.15]; ax.GridColor=[.5 .5 .5];
end
