# 第七版 CCF 推荐目录 · 场馆分级核对（脚本产出）

> 来源：`第七版中国计算机学会推荐国际学术会议和期刊目录（正式版）.pdf` → `参考资料/CCF目录解析/CCF目录第七版.txt`（pdftotext -layout）。
> 已知限制：该 PDF 的中文标题无法用 pdftotext 提取，因此只能按 A/B/C 标记切块 + 英文刊名/简称定位；
> 下表每行的「块内样例」用于人工确认该块确实是预期的领域（例如含 TOCS/TOS 的块 = 体系结构/并行/存储）。

## 1) 目标场馆 → 类别

| 目标 | 命中类别 | 出现行号 | 块内样例（前 3 个非空行） | 证据行 |
|---|---|---|---|---|
| TOCS | **A** | 11–26 |   1    TOCS /   2     TOS             ACM Transactions on Computer Systems       | 1    TOCS |
| TOS | **A** | 11–26 |   1    TOCS /   2     TOS             ACM Transactions on Computer Systems       | 2     TOS             ACM Transactions on Computer Systems           ACM http:// |
| TCAD | **A** | 11–26 |   1    TOCS /   2     TOS             ACM Transactions on Computer Systems       | 3   TCAD |
| TPDS | **A** | 11–26 |   1    TOCS /   2     TOS             ACM Transactions on Computer Systems       | 5    TPDS  IEEE Transactions on Computer-Aided Design of Integrated |
| TACO | **A** | 11–26 |   1    TOCS /   2     TOS             ACM Transactions on Computer Systems       | 6   TACO                                                             IEEE http:/ |
| TAAS | **B** | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         AC | 2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         ACM http:/ |
| TODAES | **B** | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         AC | 4  TODAES ACM Transactions on Design Automation of Electronic Systems ACM http:/ |
| TECS | **B** | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         AC | 6  TECS        ACM Transactions on Embedded Computing Systems         ACM  http: |
| TRETS | **B** | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         AC | 7  TRETS                                                              ACM  http: |
| TVLSI | **B** | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         AC | 8  TVLSI  ACM Transactions on Reconfigurable Technology and Systems |
| JPDC | **B** | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         AC | 9   JPDC    IEEE Transactions on Very Large Scale Integration (VLSI)  IEEE http: |
| TCC | **B** | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         AC | TCC    IEEE Transactions on Cloud Computing                        IEEE https:// |
| JSAC | **A** | 270–280 |                                            1    JSAC /                           | 1    JSAC |
| TON | **B** | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         AC | 2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         ACM http:/ |
| TMC | **A** | 270–280 |                                            1    JSAC /                           | 2    TMC   IEEE Journal on Selected Areas in Communications  IEEE http://dblp.un |
| TOIT | **B** | 281–296 |   1    TOIT /   2   TOMM                ACM Transactions on Internet Technology  | 1    TOIT |
| TOSN | **B** | 281–296 |   1    TOIT /   2   TOMM                ACM Transactions on Internet Technology  | 3    TOSN  ACM Transactions on Multimedia Computing, Communications |
| TCOM | **B** | 281–296 |   1    TOIT /   2   TOMM                ACM Transactions on Internet Technology  | 5   TCOM                                and Applications |
| TWC | **B** | 281–296 |   1    TOIT /   2   TOMM                ACM Transactions on Internet Technology  | 6    TWC                  ACM Transactions on Sensor Networks        ACM http:// |
| TNSM | **C** | 297–327 |   1                                  Ad Hoc Networks /   2      CC               | 3   TNSM   IEEE Transactions on Network and Service Management |
| Computer Networks | **B** | 281–296 |   1    TOIT /   2   TOMM                ACM Transactions on Internet Technology  | Computer Networks              Elsevier http://dblp.uni-trier.de/db/journals/cn/ |
| Computer Communications | **C** | 297–327 |   1                                  Ad Hoc Networks /   2      CC               | 2      CC                    Computer Communications            Elsevier http:// |
| TVT | 未命中（可能为中文名或拼写不同） | - | - | - |
| TIFS | **A** | 431–440 |   1    TDSC  IEEE Transactions on Dependable and Secure Computing /   2    TIFS  | 2    TIFS  IEEE Transactions on Information Forensics and Security  IEEE http:// |
| TSE | **C** | 533–615 |   1     WiSec /   2              ACM Conference on Security and Privacy in Wirel | 24  HotSec       USENIX Workshop on Hot Topics in Security             USENIX ht |
| TOPLAS | **A** | 616–629 |   1  TOPLAS                                                  ACM   http://dblp.u | 1  TOPLAS                                                  ACM   http://dblp.uni |
| TOSEM | **A** | 616–629 |   1  TOPLAS                                                  ACM   http://dblp.u | 2  TOSEM   ACM Transactions on Programming Languages and   ACM   http://dblp.uni |
| TDSC | **A** | 431–440 |   1    TDSC  IEEE Transactions on Dependable and Secure Computing /   2    TIFS  | 1    TDSC  IEEE Transactions on Dependable and Secure Computing |
| TKDE | **A** | 848–856 |   1    TODS           ACM Transactions on Database Systems         ACM      http | 3    TKDE  IEEE Transactions on Knowledge and Data Engineering   IEEE     http:/ |
| FPGA | **B** | 113–179 |   1                                                                              | 4    PODC                                                                 ACM    |
| FCCM | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 10                                                                           IEE |
| FPL | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 9                                Architectures, and Processors              ACM  |
| FPT | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 19  FPT        International Conference on Field-Programmable Technology     IEE |
| ICCD | **B** | 113–179 |   1                                                                              | 9    DATE                                  Gate Arrays                   IEEE/   |
| ICCAD | **B** | 113–179 |   1                                                                              | 10     HOT        The International Symposium on Code Generation and       ACM   |
| DATE | **B** | 113–179 |   1                                                                              | 6              ACM Symposium on Principles of Distributed Computing       ACM    |
| ASPDAC | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 7    ASAP                                                                   IEEE |
| ASP-DAC | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 8  ASP-DAC  IEEE International Conference on Application-Specific Systems,  IEEE |
| ISCA | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | MICRO            IEEE/ACM International Symposium on Microarchitecture  IEEE   h |
| MICRO | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | 9  HPCA             IEEE International Symposium on High Performance       IEEE  |
| HPCA | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | 8                                                                                |
| ASPLOS | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | 11                                                                          ACM  |
| DAC | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | 7  DAC              Design Automation Conference                           ACM   |
| HPDC | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | ASPLOS              Computing, Networking, Storage, and Analysis        IEEE/  h |
| IPDPS | **B** | 113–179 |   1                                                                              | 19  IPDPS        IEEE International Parallel & Distributed Processing        ACM |
| ICDCS | **B** | 113–179 |   1                                                                              | 11    CHIPS                                                               IEEE/  |
| ICPP | **B** | 113–179 |   1                                                                              | ACM    http://dblp.uni-trier.de/db/conf/icpp/ |
| Euro-Par | **B** | 113–179 |   1                                                                              | 25  Euro-Par     European Conference on Parallel and Distributed Computing   Spr |
| MSST | **B** | 113–179 |   1                                                                              | 23  MSST         Mass Storage Systems and Technologies                       IEE |
| SoCC | **B** | 113–179 |   1                                                                              | 2     SoCC                ACM Symposium on Cloud Computing                ACM    |
| CLUSTER | **B** | 113–179 |   1                                                                              | 8                                                                         ACM    |
| CCGRID | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 15  CCGRID     IEEE/ACM International Symposium on Cluster, Cloud and        IEE |
| NPC | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 16  NPC        IFIP International Conference on Network and Parallel         Spr |
| SYSTOR | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 4  SYSTOR   ACM International Systems and Storage Conference                ACM  |
| CoNEXT | **B** | 341–371 |   1 /   2    SenSys     ACM Conference on Embedded Networked Sensor Systems      | 3   CoNEXT                                                                       |
| ICNP | **B** | 341–371 |   1 /   2    SenSys     ACM Conference on Embedded Networked Sensor Systems      | MobiSys  IEEE International Conference on Sensing, Communication, and     IEEE/  |
| IWQoS | **B** | 341–371 |   1 /   2    SenSys     ACM Conference on Embedded Networked Sensor Systems      | 10                                                                               |
| IMC | **B** | 341–371 |   1 /   2    SenSys     ACM Conference on Embedded Networked Sensor Systems      | NOSSDAV          ACM International Conference on Mobile Systems,           IEEE/ |
| INFOCOM | **A** | 328–340 |   1  SIGCOMM /   2   MobiCom  ACM International Conference on Applications, Tech | 3  INFOCOM    Architectures, and Protocols for Computer Communication |
| SIGCOMM | **A** | 328–340 |   1  SIGCOMM /   2   MobiCom  ACM International Conference on Applications, Tech | 1  SIGCOMM |
| NSDI | **A** | 328–340 |   1  SIGCOMM /   2   MobiCom  ACM International Conference on Applications, Tech | NSDI                                 Networking |
| MobiCom | **A** | 328–340 |   1  SIGCOMM /   2   MobiCom  ACM International Conference on Applications, Tech | 2   MobiCom  ACM International Conference on Applications, Technologies,  ACM ht |
| MobiSys | **B** | 341–371 |   1 /   2    SenSys     ACM Conference on Embedded Networked Sensor Systems      | 6     IPSN                                                                     I |
| SenSys | **B** | 341–371 |   1 /   2    SenSys     ACM Conference on Embedded Networked Sensor Systems      | 2    SenSys     ACM Conference on Embedded Networked Sensor Systems            A |
| SEC | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 26  SEC        ACM/IEEE Symposium on Edge Computing                          IEE |
| ICPADS | **C** | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers          | 20  ICPADS     International Conference on Parallel and Distributed Systems  IEE |
| GLOBECOM | **C** | 372–430 |   1      ANCS                                                              IEEE/ | 5                  Asia-Pacific Network Operations and Management       Springer |
| OSDI | **A** | 687–715 |   1    PLDI                                                                      | 9   ISSTA                          Software Engineering                 IEEE/  h |
| SOSP | **A** | 687–715 |   1    PLDI                                                                      | 4    SOSP                                                                ACM   h |
| FAST | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | 2    FAST           ACM SIGPLAN Symposium on Principles & Practice of      ACM h |
| ATC | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | ACM SIGOPS ATC  ACM SIGOPS Annual Technical Conference                 IEEE |
| EuroSys | **A** | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practi | SC                International Conference for High Performance      ACM    http |
| Middleware | **B** | 716–771 |   1   ECOOP /   2   ETAPS    European Conference on Object-Oriented Programming  | 15  Middleware  International Middleware Conference                        ACM/I |
| SIGMOD | **A** | 932–948 |   1  SIGMOD /   2  SIGKDD                     ACM SIGMOD Conference              | 1  SIGMOD |
| VLDB | **A** | 848–856 |   1    TODS           ACM Transactions on Database Systems         ACM      http | 4   VLDBJ                                                       Springer  http:/ |
| ICDE | **A** | 932–948 |   1  SIGMOD /   2  SIGKDD                     ACM SIGMOD Conference              | 4    ICDE                                                         ACM http://dbl |

## 2) 全部分块索引（供人工核对块的真实领域）

| 块 | 类别 | 行号 | 前 5 个非空行 |
|---|---|---|---|
| #1 | A | 11–26 |   1    TOCS /   2     TOS             ACM Transactions on Computer Systems           ACM http://dblp.uni-trier |
| #2 | B | 27–49 |   1 /   2  TAAS   ACM Transactions on Autonomous and Adaptive Systems         ACM http://dblp.uni-trier.de/db/ |
| #3 | C | 50–81 |   1 /   2  JETC ACM Journal on Emerging Technologies in Computing Systems            ACM http://dblp.uni-trier |
| #4 | A | 82–112 |   1   PPoPP /   2    FAST           ACM SIGPLAN Symposium on Principles & Practice of      ACM http://dblp.uni |
| #5 | B | 113–179 |   1                                                                               http://dblp.uni-trier.de/db/ |
| #6 | C | 180–269 |   1 /   2  CF       ACM International Conference on Computing Frontiers             ACM http://dblp.uni-trier. |
| #7 | A | 270–280 |                                            1    JSAC /                                            2    TMC   I |
| #8 | B | 281–296 |   1    TOIT /   2   TOMM                ACM Transactions on Internet Technology      ACM http://dblp.uni-trier |
| #9 | C | 297–327 |   1                                  Ad Hoc Networks /   2      CC                    Computer Communications  |
| #10 | A | 328–340 |   1  SIGCOMM /   2   MobiCom  ACM International Conference on Applications, Technologies,  ACM http://dblp.uni |
| #11 | B | 341–371 |   1 /   2    SenSys     ACM Conference on Embedded Networked Sensor Systems            ACM   http://dblp.uni-t |
| #12 | C | 372–430 |   1      ANCS                                                              IEEE/    http://dblp.uni-trier.de/d |
| #13 | A | 431–440 |   1    TDSC  IEEE Transactions on Dependable and Secure Computing /   2    TIFS  IEEE Transactions on Informat |
| #14 | B | 441–457 |   1    TOPS         ACM Transactions on Privacy and Security /   2                                             |
| #15 | C | 458–483 |   1    CLSR /   2           Computer Law & Security Review                    Elsevier https://dblp.org/db/jou |
| #16 | A | 484–500 |   1          CCS        ACM Conference on Computer and Communications /   2                                    |
| #17 | B | 501–532 |   1 /   2     ACSAC      Annual Computer Security Applications Conference           IEEE https://dblp.uni-trie |
| #18 | C | 533–615 |   1     WiSec /   2              ACM Conference on Security and Privacy in Wireless and       ACM http://dblp. |
| #19 | A | 616–629 |   1  TOPLAS                                                  ACM   http://dblp.uni-trier.de/db/journals/toplas |
| #20 | B | 630–655 |   1     ASE         Automated Software Engineering            Springer   http://dblp.uni-trier.de/db/journals/ |
| #21 | C | 656–686 |   1      CL /   2                     Computer Languages, Systems and Structures         Elsevier    http://db |
| #22 | A | 687–715 |   1    PLDI                                                                      http://dblp.uni-trier.de/db/c |
| #23 | B | 716–771 |   1   ECOOP /   2   ETAPS    European Conference on Object-Oriented Programming       AITO http://dblp.uni-tri |
| #24 | C | 772–847 |   1     PEPM /   2    PASTE       ACM SIGPLAN Workshop on Partial Evaluation and           ACM http://dblp.uni |
| #25 | A | 848–856 |   1    TODS           ACM Transactions on Database Systems         ACM      http://dblp.uni-trier.de/db/journa |
| #26 | B | 857–889 |   1   TKDD    ACM Transactions on Knowledge Discovery from Data /   2   TWEB                                   |
| #27 | C | 890–931 |   1     DPD                  Distributed and Parallel Databases /   2     I&M                                  |
| #28 | A | 932–948 |   1  SIGMOD /   2  SIGKDD                     ACM SIGMOD Conference               ACM http://dblp.uni-trier.de |
| #29 | B | 949–984 |   1                                                                         ACM /   2      CIKM          ACM I |
| #30 | C | 985–1022 |   1   APWeb /   2   DEXA                    Asia Pacific Web Conference                     Springer http://db |
| #31 | A | 1023–1030 |   1     TIT  IEEE Transactions on Information Theory   IEEE     http://dblp.uni-trier.de/db/journals/tit/ /    |
| #32 | B | 1031–1062 |   1      TALG             ACM Transactions on Algorithms /   2      TOCL       ACM Transactions on Computation |
| #33 | C | 1063–1094 |   1      ACTA                   Acta Informatica /   2      APAL        Annals of Pure and Applied Logic   Spr |
| #34 | A | 1095–1107 |   1    STOC                                                            ACM      http://dblp.uni-trier.de/db/co |
| #35 | B | 1108–1132 |   1    SoCG /   2     ESA     International Symposium on Computational Geometry     ACM https://dblp.uni-trier |
| #36 | C | 1133–1169 |   1 /           CSL                    Computer Science Logic                   Springer      http://dblp.uni- |
| #37 | A | 1170–1181 |   1    TOG                                                     ACM   http://dblp.uni-trier.de/db/journals/tog/ |
| #38 | B | 1182–1205 |   1   TOMM        ACM Transactions on Multimedia Computing,                           ACM /   2   CAGD         |
| #39 | C | 1206–1245 |   1   CGTA /   2   CAVW    Computational Geometry: Theory and Applications  Elsevier http://dblp.uni-trier.de/ |
| #40 | A | 1246–1257 |   1   ACM MM                                                                ACM /   2  SIGGRAPH           ACM  |
| #41 | B | 1258–1292 |   1      ICMR          ACM SIGMM International Conference on Multimedia                   http://dblp.uni-trie |
| #42 | C | 1293–1342 |   1 /           VRST             ACM Symposium on Virtual Reality Software and Technology          ACM http:// |
| #43 | A | 1343–1354 |   1      AI /   2                             Artificial Intelligence         Elsevier http://dblp.uni-trier.d |
| #44 | B | 1355–1407 |   1     TAP /   2                  ACM Transactions on Applied Perception      ACM http://dblp.uni-trier.de/db |
| #45 | C | 1408–1505 |   1  TALLIP /   2           ACM Transactions on Asian and Low-Resource Language  ACM http://dblp.uni-trier.de/ |
| #46 | A | 1506–1524 |   1    AAAI /   2  NeurIPS         AAAI Conference on Artificial Intelligence     AAAI http://dblp.uni-trier.d |
| #47 | B | 1525–1563 |   1    COLT /   2  EMNLP    Annual Conference on Computational Learning Theory         Springer                |
| #48 | C | 1564–1629 |   1  AISTATS                                                            JMLR               http://dblp.uni-tri |
| #49 | A | 1630–1635 |   1   TOCHI   ACM Transactions on Computer-Human Interaction    ACM      http://dblp.uni-trier.de/db/journals/ |
| #50 | B | 1636–1660 |   1    CSCW /   2     HCI                Computer Supported Cooperative Work           Springer   http://dblp. |
| #51 | C | 1661–1677 |   1      BIT              Behaviour & Information Technology        Taylor &  http://dblp.uni-trier.de/db/jour |
| #52 | A | 1678–1693 |   1   CSCW                                                           ACM  http://dblp.uni-trier.de/db/conf/csc |
| #53 | B | 1694–1718 |   1   GROUP                                                                ACM      http://dblp.uni-trier.de/d |
| #54 | C | 1719–1765 |   1         DIS                                                                  ACM     http://dblp.uni-trier |
| #55 | A | 1766–1778 |   1      JACM                  Journal of the ACM                           http://dblp.uni-trier.de/db/journa |
| #56 | B | 1779–1819 |   1             Briefings in Bioinformatics                                                 http://dblp.uni-tr |
| #57 | C | 1820–1862 |   1 /   2             BMC Bioinformatics                                           BioMed Central http://dblp. |
| #58 | A | 1863–1870 |   1   WWW                      The Web Conference       ACM   http://dblp.uni-trier.de/db/conf/www/ /   2    R |
| #59 | B | 1871–1892 |   1   CogSci /   2    BIBM      Annual Meeting of the Cognitive Science Society     Psychology  https://dblp.u |
| #60 | C | 1893–1923 |   1       AMIA        American Medical Informatics Association Annual /   2      APBC                          |

## 3) 未命中清单

- TVT
