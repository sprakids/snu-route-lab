
function makeBusArvlInfo(arsId, headerType) {
	var req = {
		"arsId" : arsId.replace(/\s+/g,'')
	};
	jQuery
			.ajax( {
				type : 'POST',
				dataType : 'json',
				url : '/mBus/bus/getStationByUid.bms',
				data : req,
				success : function(data) {
					if (data.error.errorCode == '0000') {
						var pageSize = getWindowSize();

						var windowWidth = pageSize[0];
						var windowHeight = pageSize[1];
						var nextHeaderType = '';

						makeHeader(headerType);
						if (headerType == 'arsId') {
							nextHeaderType = 'busUnique';
						} else if (headerType == 'busArvl') {
							nextHeaderType = 'busRoute';
						} else if (headerType == 'bookmarkArsId') {
							nextHeaderType = 'bookmarkArvl';
						} else {
							nextHeaderType = 'busStation';
						}

						for ( var i = 0; i < data.resultList.length; i++) { //심야21A ~ 20231204
							if(data.resultList[i].busRouteId==101000005){
								data.resultList[i].rtNm = '심야A21(자율주행)(토,일 미운행)';
							}
						}

						var temp = '';
						if (data.resultList != null) {
							temp += '<div class="fstTab">'
									+ data.resultList[0].stNm
									+ '['
									+ arsId
									+ ']'
									+ '<img src="./images/bus/favorite.png" alt="즐겨찾기" class="bookmark" onclick="setBookMark(\''
									+ data.resultList[0].stNm + '\' , \''
									+ arsId + '\' , \'\', \'ARSID\')">'
									+ '</div>';

							var airYn, redYn, blueYn, greenYn, yellowYn, iBusYn, gBusYn, tBusYn, vilBusYn, hanriverYn = false;

							for ( var i = 0; i < data.resultList.length; i++) {
								if (data.resultList[i].routeType == 1) {
									airYn = true;
								} else if (data.resultList[i].routeType == 2) {
									/* 210.96.13.90서버 용 */
									vilBusYn = true;
								} else if (data.resultList[i].routeType == 3) {
									blueYn = true;
								} else if (data.resultList[i].routeType == 4) {
									greenYn = true;
								} else if (data.resultList[i].routeType == 5) {
									yellowYn = true;
								} else if (data.resultList[i].routeType == 6) {
									redYn = true;
								} else if (data.resultList[i].routeType == 7) {
									iBusYn = true;
								} else if (data.resultList[i].routeType == 8) {
									gBusYn = true;
								} else if (data.resultList[i].routeType == 10) {
									tBusYn = true;
								} else if (data.resultList[i].routeType == 14) {
									hanriverYn = true;
								}
							}

							if (blueYn) {
								temp += '<div class="blueBus"> <div class="txtA"> <img src="./images/bus/blueicon.png" alt="간선버스" class="busIcon"> <span class="busAlingTxt"> 간선버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 3) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busBlueCol">';
										temp += '<img src="./images/bus/bluebus.png" alt="간선버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';

										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}


										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}

							if (greenYn) {
								temp += '<div class="greenBus"> <div class="txtA"> <img src="./images/bus/greenicon.png" alt="지선버스" class="busIcon"> <span class="busAlingTxt"> 지선버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 4) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busGreenCol">';
										temp += '<img src="./images/bus/greenbus.png" alt="지선버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';


										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}

										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}

							if (yellowYn) {
								temp += '<div class="yellowBus"> <div class="txtA"> <img src="./images/bus/yellowicon.png" alt="순환버스" class="busIcon"> <span class="busAlingTxt"> 순환버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 5) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busYellowCol">';
										temp += '<img src="./images/bus/yellowbus.png" alt="순환버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';

										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}

										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}

							if (vilBusYn) {
								temp += '<div class="greenBus"> <div class="txtA"> <img src="./images/bus/greenicon.png" alt="마을버스" class="busIcon"> <span class="busAlingTxt"> 마을버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 2) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busGreenCol">';
										temp += '<img src="./images/bus/greenbus.png" alt="마을버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';

										temp += '<div class="arvlTime">';

										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}

										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}

							if (redYn) {
								temp += '<div class="redBus"> <div class="txtA">  <img src="./images/bus/redicon.png" alt="광역버스" class="busIcon"> <span class="busAlingTxt"> 광역버스 </span>  </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 6) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busRedCol">';
										temp += '<img src="./images/bus/redbus.png" alt="광역버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';


										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}

										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}

							if (airYn) {
								temp += '<div class="redBus"> <div class="txtA"> <img src="./images/bus/redicon.png" alt="공항버스" class="busIcon"> <span class="busAlingTxt"> 공항버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 1) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busRedCol">';
										temp += '<img src="./images/bus/redbus.png" alt="공항버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';

										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}

										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}

							if (gBusYn) {
								temp += '<div class="redBus"> <div class="txtA"> <img src="./images/bus/redicon.png" alt="경기버스" class="busIcon"> <span class="busAlingTxt"> 경기버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 8) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busRedCol">';
										temp += '<img src="./images/bus/gbus.png" alt="경기버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';


										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}

										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}

							if (tBusYn) {
								temp += '<div class="orangeBus"> <div class="txtA"> <img src="./images/bus/orangeicon.png" alt="관광" class="busIcon"> <span class="busAlingTxt"> 관광버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 10) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busOrangeCol">';
										temp += '<img src="./images/bus/orangebus.png" alt="관광버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';


										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}

										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}

							if (iBusYn) {
								temp += '<div class="redBus"> <div class="txtA"> <img src="./images/bus/redicon.png" alt="광역버스" class="busIcon"> <span class="busAlingTxt"> 인천버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 7) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum busRedCol">'
										temp += '<img src="./images/bus/ibus.png" alt="인천버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';

										/*만차여부*/
										var isFullFlag1 = data.resultList[i].isFullFlag1;
										var isFullFlag2 = data.resultList[i].isFullFlag2;

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										/*만약 차량 ID가 0이하며, 운행중인 차량이 없으므로, [만차] 문구도 보내지 않음*/
										if(vehId1 == '0') { isFullFlag1 = '0'; }
										if(vehId2 == '0') { isFullFlag2 = '0'; }

										var strFullMsg1 = '';
										var strFullMsg2 = '';

										if(isFullFlag1 == '1'){strFullMsg1 = '<font color=red> [만차]</font>';}
										if(isFullFlag2 == '1'){strFullMsg2 = '<font color=red> [만차]</font>';}

										//우회 여부 // 무정차 추가 _ads_ 250326
										//버스파업 추가 _ads_ 260909
										if (data.resultList[i].detourAt == '11') {
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
										} else if (data.resultList[i].detourAt == '13') {
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
										} else if (data.resultList[i].detourAt == '16') {
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
											temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
										} else {
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 + strFullMsg1 +'</div>';
											temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 + strFullMsg2 +'</div>';
										}

										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}
							}
							if (hanriverYn) {
								temp += '<div class="blueBus"> <div class="txtA"> <img src="./images/bus/hanrivericon.png" alt="한강버스" style="width:18px" class="busIcon"> <span class="busAlingTxt"> 한강버스 </span> </div> </div>';

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 14) {
										var minValue1, modValue1, minValue2, modValue2 = false;
										var vehId1Exist, vehId2Exist = false;
										var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
										var sectOrd1, sectOrd2 = 0;
										if (data.resultList[i].vehId1 != 0) {
											if (data.resultList[i].traTime1 != 0) {
												vehId1Exist = true;
												traTimeMin1 = parseInt(data.resultList[i].traTime1 / 60);
												if (traTimeMin1 > 0) {
													minValue1 = true;
												}
												traTimeSec1 = parseInt(data.resultList[i].traTime1 % 60);
												if (traTimeSec1 > 0) {
													modValue1 = true;
												}
												sectOrd1 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd1));
											}
										}

										if (data.resultList[i].vehId2 != 0) {
											if (data.resultList[i].traTime2 != 0) {
												vehId2Exist = true;
												traTimeMin2 = parseInt(data.resultList[i].traTime2 / 60);
												if (traTimeMin2 > 0) {
													minValue2 = true;
												}
												traTimeSec2 = parseInt(data.resultList[i].traTime2 % 60);
												if (traTimeSec2 > 0) {
													modValue2 = true;
												}
												sectOrd2 = Math
														.abs(Number(data.resultList[i].staOrd)
																- Number(data.resultList[i].sectOrd2));
											}
										}

										temp += '<div class="busArvlInfo" onclick="makeRouteList(\''
												+ data.resultList[i].busRouteId
												+ '\' , \''
												+ nextHeaderType
												+ '\')">';
										temp += '<div class="ntInfo"> <div class="busNum '+ (data.resultList[i].rtNm.includes("급") ? "busOrangeCol" : "busBlueCol" ) +'">'
										temp += '<img src="./images/bus/'+ (data.resultList[i].rtNm.includes("급") ? "orangebus" : "bluebus" ) +'.png" alt="한강버스" class="busMark">';
										temp += '<span class="busNumvAling">'
												+ data.resultList[i].rtNm
												+ '</span>';
										temp += '</div>';
										temp += '<div class="arvlTime">';

										/*차량번호*/
										var vehId1 = data.resultList[i].vehId1;
										var vehId2 = data.resultList[i].vehId2;

										temp += '<div class="dtlTime">' + data.resultList[i].arrmsg1 +'</div>';
										temp += '<div class="dtlTime">' + data.resultList[i].arrmsg2 +'</div>';
										temp += '</div>';
										temp += '</div>';
										temp += '<div class="feInfo"> <div class="feTxt">'
												+ data.resultList[i].adirection
												+ '방면 / 전일운행 : '
												+ data.resultList[i].firstTm
												+ '~'
												+ data.resultList[i].lastTm
												+ '</div> </div>';
										temp += '</div>';
									}
								}

							}
						} else {
							temp += '<div class="noResult"> 검색결과가 없습니다. 버스정류장 ID 를 확인해 주세요. </div>';
						}
						$('#busArvlInfo').html(temp);

						$('.feTxt').css("width", windowWidth - 18);

						if ($('#arsIdList').css("display") == 'block') {
							$('#arsIdList').hide();
						}
						if ($('#busArvlInfo').css("display") == 'none') {
							$('#busArvlInfo').show();
						}

						if ($('#busRouteList').css("display") == 'block') {
							$('#busRouteList').hide();
						}
					} else {
						alert(data.error.errorMessage);
					}
				},
				error : function() {
					alert("네트워크가 불안정합니다. 다시 시도해 주시기 바랍니다.");
				}
			});
}


function makeRouteList(busRouteId, headerType) {

	var req = {
		"busRouteId" : busRouteId
	};
	jQuery.ajax( {
				type : 'POST',
				dataType : 'json',
				url : '/mBus/bus/getRouteAndPos.bms',
				data : req,
				success : function(data) {

					if (data.error.errorCode == '0000') {
						var pageSize = getWindowSize();

						var windowWidth = pageSize[0];
						var windowHeight = pageSize[1];

						makeHeader(headerType);


						if (data.resultList != null) {

							var temp = '';

							temp += '<div class="fstTab">';
							temp += '<div class="leftImg" onclick="makeRouteInfo(\''
									+ busRouteId + '\')"> <button style="-moz-border-radius: 5px; -webkit-border-radius: 5px;background:#01aeef;width: 88px;height: 25px;font-weight:bolder;color:#ffffff;" value="노선정보">노선정보</button> </div>';
							temp += '<font id="busRouteNmCk">' + data.resultList[0].busRouteFullNm + '</font>';
							temp += '<img style="position:relative;left:8px;top:4px" id="routeBookMark2" src="./images/bus/favorite.png" alt="즐겨찾기">';

							temp += data.resultList[0].routeType == '14' ? '' : '<div class="rightImg"> </div>';
							temp += '</div>';

							for ( var i = 0; i < data.resultList.length; i++) {
								var detourYn = data.resultList[i].detourAt == '11';
								var detourYn_nostop = data.resultList[i].detourAt == '13';
								var detourYn_strike = data.resultList[i].detourAt == '16';

								var stationNm = "";
								// var stationNm =	detourYn ? '<span style=color:blue;>' + data.resultList[i].stationNm + '<span>'+ '(우회)' : data.resultList[i].stationNm;

								if(detourYn) {
									stationNm = '<span style=color:blue;>' + data.resultList[i].stationNm + '<span>'+ '(우회)'
								} else if (detourYn_nostop) {
									stationNm = '<span style=color:blue;>' + data.resultList[i].stationNm + '<span>'+ '(무정차)'
								} else if (detourYn_strike) {
									stationNm = '<span style=color:blue;>' + data.resultList[i].stationNm + '<span>'+ '(버스파업)'
								} else {
									stationNm = data.resultList[i].stationNm;
								}

								// 가상정류장 이름을 회색 + 클릭이벤트 제거 260818 _ads_
								// var VirtualSttnYn = ((data.resultList[i].routeType == "3" || data.resultList[i].routeType == "4") && data.resultList[i].stationNo.includes("미정차")) ? true : false;
								var VirtualSttnYn = data.resultList[i].stationNo.includes("미정차") ? true : false;

								if(VirtualSttnYn) {
									temp += '<div class="BusRouteLine" style="color:#ddd;">';
								} else {
									temp += '<div class="BusRouteLine" onclick="makeBusArvlInfoAsRouteId(\''
										+ data.resultList[i].station
										+ '\' ,\''
										+ data.resultList[i].busRouteId
										+ '\' ,\''
										+ data.resultList[i].seq
										+ '\')">';
								}
								temp += '<div class="BusRouteInfo">';
								temp += '<div id="BusStNm'+i+'" class="BusStNm">';

								temp += stationNm;

								temp += '</div>';

								temp += '<div class="BusStNum">';
								if (data.resultList[i].stationNo != 0) {
									temp += data.resultList[i].stationNo;
								}
								temp += '</div>';
								temp += '</div>';
								temp += '<div class="BusRouteSpeed">';
								temp += '<div tabindex="0" title="a" class="'
										+ (data.resultList[i].routeType == "14" ? "NoSpeed" : data.resultList[i].sectSpdCol) + '">';
								// 한강버스의 경우 구간속도 정보를 제공하지 않는다. 250908 _ads_

								if (data.resultList[i].transYn == 'Y' && data.resultList[i].routeType != '14') { //회차지점인 경우 && 한강버스가 아닌 경우 (한강버스는 회차지를 무시한다.) 250908 _ads_
									temp += '<div class="transMark">';

									if (data.resultList[i].existYn == 'Y') {

										// 간선버스
										if (data.resultList[i].routeType == '3') {

											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;right:28px;">';
											// 차량 개수만큼 반복
											$.each(data.resultList[i].vehList, function(j, v) {
												//만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="BlueBusFull"></div>';
												} else {
													if(v.busType == '0') { //일반
														temp += '<div class="BlueBus0"></div>';
													} else if (v.busType == '1') { //저상
														temp += '<div class="BlueBus1"></div>';
													} else if (v.busType == '2' || v.busType == '3') { //타요
														temp += '<div class="BlueBus2"></div>';
													}
												}
											});
											temp += '</div>';
										}	//end routeType = 3


										if (data.resultList[i].routeType == '4'
												|| data.resultList[i].routeType == '2') {

											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;right:28px;">';
											// 차량 개수만큼 반복
											$.each(data.resultList[i].vehList, function(j, v) {
												//만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="GreeneBusFull"></div>';
												} else {
													if (v.busType == '0') {
														temp += '<div class="GreenBus0"></div>';
													} else if (v.busType == '1') {
														temp += '<div class="GreenBus1"></div>';
													} else if (v.busType == '4' || v.busType == '5') {
														temp += '<div class="GreenBus2"></div>';
													} else if (v.busType == '8' || v.busType == '9') {
														temp += '<div class="GreenBus3"></div>';
													}
												}
											});
											temp += '</div>';
										}	// end routeType = 4


										if (data.resultList[i].routeType == '5') {
											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;right:28px;">';
											// 차량 개수만큼 반복
											$.each(data.resultList[i].vehList, function(j, v) {
												//만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="YellowBusFull"></div>';
												}
												//막차 여부 확인
												else if(v.islastyn == '1'){
													temp += '<div class="YellowBusLast"></div>';
												}
												else {
													temp += '<div class="YellowBus0"></div>';
												}
											});
											temp += '</div>';
										}

										//광역, 공항, 인천, 경기
										if (data.resultList[i].routeType == '1' || data.resultList[i].routeType == '6'
												|| data.resultList[i].routeType == '7' || data.resultList[i].routeType == '8') {

											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;right:28px;">';
											// 차량 개수만큼 반복
											$.each(data.resultList[i].vehList, function(j, v) {
												//만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="RedBusFull"></div>';
												}
												// 막차 여부 확인
												else if(v.islastyn == '1'){
													temp += '<div class="OrangeBusLast"></div>';
												}
												else {
													if(data.resultList[i].busType == '0'){
														temp += '<div class="OrangeBus0"></div>';
													} else if(data.resultList[i].busType == '6' || data.resultList[i].busType == '7'){
														temp += '<div class="OrangeBus1"></div>';
													}
												}
											});
											temp += '</div>';
										}

										//관광
										if (data.resultList[i].routeType == '10') {
											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;right:28px;">';
											// 차량 개수만큼 반복
											$.each(data.resultList[i].vehList, function(j, v) {
												//만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="RedOrangeFull"></div>';

												} else {
													if(data.resultList[i].busType == '0'){
														temp += '<div class="OrangeBus0"></div>';
													} else if(data.resultList[i].busType == '6' || data.resultList[i].busType == '7'){
														temp += '<div class="OrangeBus1"></div>';
													}
												}
											});
											temp += '</div>';
										}
									}

									temp += '</div>';

								} else {
									if (data.resultList[i].existYn == 'Y') {

										//간선 버스
										if (data.resultList[i].routeType == '3') {
											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;">';
											$.each(data.resultList[i].vehList, function(j, v) {

												// 만차 여부 확인
												if(v.isFullFlag == '1') {

													temp += '<div class="BlueBusFull"></div>';
												}
												// 막차 여부 확인
												else if(v.islastyn == '1') {

													temp += '<div class="BlueBusLast"></div>';
												}
												else {

													var busType = data.resultList[i].busType == "3" ? "2" : data.resultList[i].busType;
													var busClassId = "BlueBus" + busType;

													var lastStnOrd3 = data.resultList[i].lastStnOrd3;
													var confuseBus = lastStnOrd3 == "images/bus/confuse_green.png" ? "ConfuseBus3" : lastStnOrd3 == "images/bus/confuse_blue.png" ? "ConfuseBus2" : lastStnOrd3 == "images/bus/confuse_red.png" ? "ConfuseBus1" : "ConfuseBus4";

													temp += '<div class="' + busClassId + '"></div><div class="' + confuseBus + '"></div>';

												}
											});
											temp += '</div>';
										}

										//지선 및 마을 버스
										if (data.resultList[i].routeType == '4' || data.resultList[i].routeType == '2') {
											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;">';
											$.each(data.resultList[i].vehList, function(j, v) {
												// 만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="GreenBusFull"></div>';
												}
												// 막차 여부 확인
												else if(v.islastyn == '1'){
													temp += '<div class="GreenBusLast"></div>';
												}
												else {
													if (v.busType == '0') {
														temp += '<div class="GreenBus0"></div>';
													} else if (v.busType == '1') {
														temp += '<div class="GreenBus1"></div>';
													} else if (v.busType == '4' || v.busType == '5') {
														temp += '<div class="GreenBus2"></div>';
													} else if (v.busType == '8' || v.busType == '9') {
														temp += '<div class="GreenBus3"></div>';
													}
												}
											});
											temp += '</div>';
										}

										//순환버스 만차여부 확인
										if (data.resultList[i].routeType == '5') {
											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;">';
											$.each(data.resultList[i].vehList, function(j, v) {
												// 만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="YelloBusFull"></div>';
												} else {
													temp += '<div class="YellowBus0"></div>';
												}
											});
											temp += '</div>';
										}

										//광역, 공항, 경기, 인천 버스 만차여부 확인
										if (data.resultList[i].routeType == '1'
												|| data.resultList[i].routeType == '6'
												|| data.resultList[i].routeType == '7'
												|| data.resultList[i].routeType == '8') {

											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;">';
											$.each(data.resultList[i].vehList, function(j, v) {
												// 만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="RedBusFull"></div>';
												}
												// 막차 여부 확인
												else if(v.islastyn == '1'){
													temp += '<div class="RedBusLast"></div>';
												}
												else {
													if(data.resultList[i].busType == '0'){
														temp += '<div class="RedBus0"></div>';
													} else if(data.resultList[i].busType == '6'
																	|| data.resultList[i].busType == '7'){
														temp += '<div class="RedBus1"></div>';
													}
												}

											});
											temp += '</div>';
										}

										//관광
										if (data.resultList[i].routeType == '10') {
											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;">';
											$.each(data.resultList[i].vehList, function(j, v) {
												// 만차 여부 확인
												if(v.isFullFlag == '1'){
													temp += '<div class="OrangeBusFull"></div>';
												}
												// 막차 여부 확인
												else if(v.islastyn == '1'){
													temp += '<div class="OrangeBusLast"></div>';
												}
												else {
													if(data.resultList[i].busType == '0'){
														temp += '<div class="OrangeBus0"></div>';
													} else if(data.resultList[i].busType == '6'
																	|| data.resultList[i].busType == '7'){
														temp += '<div class="OrangeBus1"></div>';
													}
												}

											});
											temp += '</div>';
										}

										// 한강버스
										if (data.resultList[i].routeType == '14') {
											temp += '<div class="BusImg" style="width:' + (48 * data.resultList[i].vehList.length) + 'px;">';
											$.each(data.resultList[i].vehList, function(j, v) {
												temp += '<div class="hanRiverBus0"></div>';
											});
											temp += '</div>';
										}

									}	//end if (data.resultList[i].existYn == 'Y')
								}
								temp += '</div>';
								temp += '</div>';
								temp += '</div>';

							}

						}

						$("#busRouteList").html(temp);

						$(".BusRouteInfo").css("width", windowWidth - 70);

						if ($('#busArvlInfo').css("display") == 'block') {
							$('#busArvlInfo').hide();
						}

						if ($('#arsIdList').css("display") == 'block') {
							$('#arsIdList').hide();
						}

						if ($('#busRouteList').css("display") == 'none') {
							$('#busRouteList').show();
						}

						$("#routeBookMark2").click(function() {
							setBookMark( busRouteId, data.resultList[0].busRouteFullNm,'' , 'ROUTENM');
						});

						$("#busRouteNmCk").click(function() {
							makeRouteList(busRouteId, headerType);
						});

					} else {
						alert(data.error.errorMessage);
					}
				},
				error : function() {
					alert("네트워크가 불안정합니다. 다시 시도해 주시기 바랍니다.");
				}
			});
}

function makeRouteInfo(busRouteId) {
	var req = {
		"busRouteId" : busRouteId
	};
	jQuery.ajax( {
		type : 'POST',
		dataType : 'json',
		url : '/mBus/bus/getRouteInfo.bms',
		data : req,
		success : function(data) {
			if(data.error.errorCode == '0000') {
				var pageSize = getWindowSize();

				var windowWidth  = pageSize[0];
				var windowHeight = pageSize[1];

				var temp = '';

				if (data.resultList != null) {

					temp += '<div class="bg"> </div>';
					temp += '<div id="layerOut" class="layerOut">';
					temp += '<div id="layerIn" class="layerIn">';

					temp += '<div class="routeInfo">';
					temp += '<table>';
					temp += '<tr> <td class="routeNm" colspan="2">' + data.resultList[0].busRouteNm + '번 노선정보</td> </tr>';
					temp += '<tr> <td class="dept"> 배차간격 </td> <td class="cont">' + data.resultList[0].term + '분</td> </tr>';
					temp += '<tr> <td class="dept"> 첫차 </td> <td class="cont">' + convertTime(data.resultList[0].firstBusTm) + '</td> </tr>';
					temp += '<tr> <td class="dept"> 막차 </td> <td class="cont">' + convertTime(data.resultList[0].lastBusTm) + '</td> </tr>';
					temp += '<tr> <td class="dept"> 기점 </td> <td class="cont">' + data.resultList[0].stStationNm + '</td> </tr>';
					temp += '<tr> <td class="dept"> 종점 </td> <td class="cont">' + data.resultList[0].edStationNm + '</td> </tr>';
					temp += '<tr> <td class="dept"> 운수사 </td> <td class="cont">' + data.resultList[0].corpNm + '</td> </tr>';
					temp += '</table>';
					temp += '</div>';

					temp += '<div id="closeLayer" class="closeLayer"> <div class="close">  닫기  </div> </div>';

					temp += '</div>';
					temp += '</div>';
				} else {
					temp += '<div class="bg"> </div>';
					temp += '<div id="layerOut" class="layerOut">';
					temp += '<div id="layerIn" class="layerIn">';

					temp += '<div class="busArvlAsStNm">해당 정보가 없습니다.</div>';
					temp += '<div style="border-bottom:1px solid #eee;"></div>';
					temp += '<div id="closeLayer" class="closeLayer"> <div class="close">  닫기  </div> </div>';

					temp += '</div>';
					temp += '</div>';
				}

				$("#busArvlInfoByRouteLayer").html(temp);

				$("#busArvlInfoByRouteLayer").fadeIn();
				$("#busArvlInfoByRouteLayer").css('height',
						document.body.clientHeight);
				$('#closeLayer').click(function() {
					$('#busArvlInfoByRouteLayer').fadeOut();
					return false;
				});

				$("#layerOut").css("width", windowWidth - 20);
				$("#layerIn").css("width", windowWidth - 26);

				var position = $('#layerOut');
				if (position.outerHeight() < windowHeight) {
//					if (isApple()) {
//						position.css('top', ($(window).scrollTop())
//								+ ((windowHeight - position
//										.outerHeight()) / 2) + 'px');
//					} else {
//						position.css('top', (windowHeight - position
//								.outerHeight())
//								/ 2 + 'px');
//					}
					position.css('top', (windowHeight - position
							.outerHeight())
							/ 2 + 'px');
				} else {
					position.css('top', '0px');
				}

				if (position.outerWidth() < $(document).width())
					position.css('margin-left', '-'
							+ position.outerWidth() / 2 + 'px');
				else
					position.css('left', '0px');

			} else {
				alert(data.error.errorMessage);
			}
		},
		error : function() {
			alert("네트워크가 불안정합니다. 다시 시도해 주시기 바랍니다.");
		}
	});
}

function makeBusArvlInfoAsRouteId(stId, busRouteId, ord) {
	var req = {
		"stId" : stId,
		"busRouteId" : busRouteId,
		"ord" : ord
	};

	jQuery.ajax({
			type : 'POST',
			dataType : 'json',
			url : '/mBus/bus/getArrInfoByRoute.bms',
			data : req,
			success : function(data) {
				if (data.error.errorCode == '0000') {
					var pageSize = getWindowSize();

					var windowWidth = pageSize[0];
					var windowHeight = pageSize[1];

					var temp = '';

					if (data.resultList != null) {

						var minValue1, modValue1, minValue2, modValue2 = false;
						var vehId1Exist, vehId2Exist = false;
						var traTimeMin1, traTimeSec1, traTimeMin2, traTimeSec2 = 0;
						var sectOrd1, sectOrd2 = 0;

						if (data.resultList[0].vehId1 != 0) {
							if (data.resultList[0].traTime1 != 0) {
								vehId1Exist = true;
								traTimeMin1 = parseInt(data.resultList[0].traTime1 / 60);

								if (traTimeMin1 > 0) {
									minValue1 = true;
								}
								traTimeSec1 = parseInt(data.resultList[0].traTime1 % 60);
								if (traTimeSec1 > 0) {
									modValue1 = true;
								}
								sectOrd1 = Math
										.abs(Number(data.resultList[0].staOrd)
												- Number(data.resultList[0].sectOrd1));
							}
						}

						if (data.resultList[0].vehId2 != 0) {
							if (data.resultList[0].traTime2 != 0) {
								vehId2Exist = true;
								traTimeMin2 = parseInt(data.resultList[0].traTime2 / 60);
								if (traTimeMin2 > 0) {
									minValue2 = true;
								}
								traTimeSec2 = parseInt(data.resultList[0].traTime2 % 60);
								if (traTimeSec2 > 0) {
									modValue2 = true;
								}
								sectOrd2 = Math
										.abs(Number(data.resultList[0].staOrd)
												- Number(data.resultList[0].sectOrd2));
							}
						}

						temp += '<div class="bg"> </div>';
						temp += '<div id="layerOut" class="layerOut">';
						temp += '<div id="layerIn" class="layerIn">';

						temp += '<div id="busArvlAsStNm" class="busArvlAsStNm">'
								+ data.resultList[0].stNm + '</div>';
						temp += '<div class="busArvlInfo">';
						temp += '<div class="ntInfo">';

						if (data.resultList[0].routeType == 1) {
							temp += '<div class="busNum busRedCol">'
									+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 2) {
							temp += '<div class="busNum busGreenCol">'
									+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 3) {
							temp += '<div class="busNum busBlueCol">'
									+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 4) {
							temp += '<div class="busNum busGreenCol">'
									+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 5) {
							temp += '<div class="busNum busYellowCol">'
									+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 6) {
							temp += '<div class="busNum busRedCol">'
									+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 7) {
							temp += '<div class="busNum busRedCol">'
									+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 8) {
							temp += '<div class="busNum busRedCol">'
									+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 10) {
							temp += '<div class="busNum busOrangeCol">'
								+ data.resultList[0].rtNm + '</div>';
						} else if (data.resultList[0].routeType == 14) {
							temp += '<div class="busNum busBlueCol">'
								+ data.resultList[0].rtNm + '</div>';
						}

						temp += '<div class="arvlTime">';

						/*만차여부*/
						var isFull1 = data.resultList[0].full1;
						var isFull2 = data.resultList[0].full2;

						var vehId1 = data.resultList[0].vehId1;
						var vehId2 = data.resultList[0].vehId2;

						var strFull1 = '';
						var strFull2 = '';

						if(vehId1 == '0'){ isFull1 = '0'; }
						if(vehId2 == '0'){ isFull2 = '0'; }

						if(isFull1 == '1'){ strFull1 = '<font color=red>[만차]</font>';}
						if(isFull2 == '1'){ strFull2 = '<font color=red>[만차]</font>';}

						/* 210.96.13.90 & m.bus.go.kr서버용  */

						//우회 여부
						//버스파업 추가 _ads_ 260909
						if (data.resultList[0].detourAt == '11') {
							temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
							temp += '<div class="dtlTime" style="color:blue;"> 우회 </div>';
						} else if(data.resultList[0].detourAt == '13') {
							temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
							temp += '<div class="dtlTime" style="color:blue;"> 무정차 </div>';
						} else if(data.resultList[0].detourAt == '16') {
							temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
							temp += '<div class="dtlTime" style="color:blue;"> 버스파업 </div>';
						}  else {
							temp += '<div class="dtlTime">' + data.resultList[0].arrmsg1 + strFull1 + '</div>';
							temp += '<div class="dtlTime">' + data.resultList[0].arrmsg2 + strFull2 + '</div>';
						}


						temp += '</div>';
						temp += '</div>';

						temp += '<div class="feInfo"> <div class="feTxt">'

						if(data.resultList[0].dir.length > 0 ) {
						temp += data.resultList[0].dir
								+ '방면 '
						}

						if(data.resultList[0].routeType != '14' ) {

						temp +=   data.resultList[0].dir.length > 0 ? '/ 전일운행 : ' : ' 전일운행 : '
								+ data.resultList[0].firstTm.substring(8,10) + ':'
								+ data.resultList[0].firstTm.substring(10,12) + '~'
								+ data.resultList[0].lastTm.substring(8, 10) + ':'
								+ data.resultList[0].lastTm.substring(10,12) + '';
						}

						temp += '</div></div></div>';

						temp += '<div id="closeLayer" class="closeLayer"> <div class="close">  닫기  </div> </div>';

						temp += '</div>';
						temp += '</div>';
					} else {
						temp += '<div class="bg"> </div>';
						temp += '<div id="layerOut" class="layerOut">';
						temp += '<div id="layerIn" class="layerIn">';

						temp += '<div class="busArvlAsStNm">해당 정보가 없습니다.</div>';
						temp += '<div style="border-bottom:1px solid #eee;"></div>';
						temp += '<div id="closeLayer" class="closeLayer"> <div class="close">  닫기  </div> </div>';

						temp += '</div>';
						temp += '</div>';
					}

					$("#busArvlInfoByRouteLayer").html(temp);

					$("#busArvlInfoByRouteLayer").fadeIn();
					$("#busArvlInfoByRouteLayer").css('height',
							document.body.clientHeight);
					$('#closeLayer').click(function() {
						$('#busArvlInfoByRouteLayer').fadeOut();
						//$('#BusStNm0').attr("tabindex","0").focus();//focus
						return false;
					});

					$("#layerOut").css("width", windowWidth - 20);
					$("#layerIn").css("width", windowWidth - 26);

					$("#busArvlAsStNm").attr("tabindex","0").focus(); //focus
					var position = $('#layerOut');
					if (position.outerHeight() < windowHeight) {
						position.css('top', (windowHeight - position
								.outerHeight())
								/ 2 + 'px');
					} else {
						position.css('top', '0px');
					}

					if (position.outerWidth() < $(document).width())
						position.css('margin-left', '-'
								+ position.outerWidth() / 2 + 'px');
					else
						position.css('left', '0px');

				} else {
					alert(data.error.errorMessage);
				}
			},
			error : function() {
				alert("네트워크가 불안정합니다. 다시 시도해 주시기 바랍니다.");
			}
		});
}

function setBookMark(stNm, arsId, subway, bookMarkType) {
	var expires = 365; // 민원에 의한 쿠키 유효일 수정 240718 _ads_
	var mCookie = getCookie("mCookie") == null ? '' : getCookie("mCookie");
	var cookieStr = bookMarkType + ":" + arsId + ":" + stNm + ":" + subway;

	if (mCookie != '') {
		mCookie = mCookie + "|" + cookieStr;
	} else {
		mCookie = mCookie + cookieStr;
	}

	setCookie("mCookie", mCookie, expires);

	alert("정상적으로 즐겨찾기에 추가되었습니다.");
}

$(function(){

});