$(document).ready(function() {

	var pageSize = getWindowSize();

	var windowWidth = pageSize[0];
	var windowHeight = pageSize[1];

	var search = decodeURIComponent(Request("search"));
	var firstLetter = decodeURIComponent(Request("firstLetter"));
	var searchType = decodeURIComponent(Request("searchType"));


	var NoFlg = "0";
	var myResult = search.match(/[0-9]/g );
	if (myResult != null) {
		if (myResult.length == search.length ) {
			// 숫자 조합인 경우
			NoFlg = "1";
		} else {
			// 숫자 + 한글 조합의 경우
			NoFlg = "2";
		}
	} else {
		// 한글만 있는 경우 // 마포순환버스 작업하며 추가. 한글만 검색해도 버스노선 검색되도록 출력. _ads_ 250124
		NoFlg = "2";
	}

	// 숫자 + 한글 조합의 경우
	// 정류장명 검색 : "S", 마을버스 검색 : "B"

	if (NoFlg == "1" || searchType == 'B') {
		if (search.length <= 4 || searchType == 'B') {
			var searchUTF = encodeURIComponent(search);
			makeSearchRouteList(searchUTF, search , 'arsId');
		} else if (search.length == 5) {
			makeBusArvlInfo(search, 'arsId');
		} else if (search.length > 4 || searchType == 'B') { // 마포순환버스 작업하며 추가. 4자리 이상 검색해도 버스노선 검색되도록 출력. _ads_ 250124
			var searchUTF = encodeURIComponent(search);
			makeSearchRouteList(searchUTF, search , 'arsId');
		}
		  else {
//							alert("버스번호는 4자리 이하 정류소 번호는 5자리 입니다.");
		}
	} else {

		if (searchType == 'B') { // 마포순환버스 작업하며 추가. 4자리 이상 검색해도 버스노선 검색되도록 출력. _ads_ 250124
			var searchUTF = encodeURIComponent(search);
			makeSearchRouteList(searchUTF, search , 'arsId');
		}

		if (firstLetter == 1) {
			makeSearchFirstLetterList(search, 'arsId');
		} else {
			makeSearchNameList(search, 'arsId');
		}
	}
	// Orientation callback event
	$('body').bind('orientationchange',function(event) {
		if (navigator.userAgent
				.search(/[iphone|ipod]/i) > -1) {
			$(".BusRouteInfo").css("width",
					windowWidth - 50);

			$("#layerOut").css("width",
					windowWidth - 20);
			$("#layerIn").css("width",
					windowWidth - 26);

			$("#busArvlInfoByRouteLayer").css('height',
					document.body.clientHeight);

			$("#layerOut").css("width", windowWidth - 20);
			$("#layerIn").css("width", windowWidth - 26);

			var position = $('#layerOut');
			if (position.outerHeight() < windowHeight) {
				position.css('top', (windowHeight - position.outerHeight())/ 2 + 'px');
			} else {
				position.css('top', '0px');
			}

			if (position.outerWidth() < $(document).width())
				position.css('margin-left', '-' + position.outerWidth() / 2 + 'px');
			else
				position.css('left', '0px');
		}
	});
});

$(window).resize(function() {
	if (navigator.userAgent.search(/[android|ipad]/i) > -1) {
		var pageSize = getWindowSize();

		var windowWidth = pageSize[0];
		var windowHeight = pageSize[1];

		$(".BusRouteInfo").css("width", windowWidth - 50);

		$("#busArvlInfoByRouteLayer").css('height',
				document.body.clientHeight);

		$("#layerOut").css("width", windowWidth - 20);
		$("#layerIn").css("width", windowWidth - 26);

		var position = $('#layerOut');
		if (position.outerHeight() < windowHeight) {
//					if (isApple()) {
//						position.css('top', ($(window).scrollTop())
//								+ ((windowHeight - position.outerHeight()) / 2)
//								+ 'px');
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
			position.css('margin-left', '-' + position.outerWidth() / 2
					+ 'px');
		else
			position.css('left', '0px');

	}

});

function showAjaxBox() {

	// 항상 화면 중앙에 나타나도록...
	var yp = document.body.scrollTop;
	var xp = document.body.scrollLeft;

	var ws = document.body.clientWidth;
	var hs = document.body.clientHeight;

	var ajaxBox = $('ajaxBox');

	ajaxBox.style.top = yp + eval
	!(hs) / 2 - 100;
	ajaxBox.style.left = xp + eval
	!(ws) / 2 - 100;

	Element.show(ajaxBox);
}

function makeHeader(type) {
	var header = '';

	if (type == 'arsId') {

		header += '<div class="tm_headerbox">';
		header += '<a id="topHome" href="javascript:void(0);"  class="logo"><img src="./images/common2015/header_logo.png"/></a>';
		header += '<a id="backKey" href="javascript:void(0);" class="btn_home">';
		header += '<button type="button" class="btn_img tm_home" title="Home"><img src="./images/common2015/btn_t_home.png" alt="Home"/></button>';
		header += '</a>';
		header += '<div class="header_title"> 버스도착정보 </div>';
		header += '</div>';

		$("#header").html(header);
		$('#backKey').click(function() {
			if(document.referrer) {
				location.href = document.referrer;
			} else {
				location.href = "./index.bms";
			}
		});

		$('#topHome').click(function() {
			location.href = "./index.bms";
		});

	} else if (type == 'busArvl') { // 호출 안할 것 같은데?

		header += '<div class="tm_headerbox">';
		header += '<a id="topHome" href="javascript:void(0);"  class="logo"><img src="./images/common2015/header_logo.png"/></a>';
		header += '<a id="backKey" href="javascript:void(0);" class="btn_home">';
		header += '<button type="button" class="btn_img tm_home" title="Home"><img src="./images/common2015/btn_t_home.png" alt="Home"/></button>';
		header += '</a>';
		header += '<div class="header_title"> 버스도착정보 </div>';
		header += '</div>';

		$("#header").html(header);
		$('#backKey').click(function() {
			$('#busArvlInfo').hide();
			if ($('#arsIdList').css("display") == 'none') {
				makeHeader('arsId');
				$('#arsIdList').show();
			}
		});

		$('#topHome').click(function() {
			location.href = "./index.bms";
		});
	} else if (type == 'busRoute') { // 호출 안할 것 같은데?

		header += '<div class="tm_headerbox">';
		header += '<a id="topHome" href="javascript:void(0);"  class="logo"><img src="./images/common2015/header_logo.png"/></a>';
		header += '<a id="backKey" href="javascript:void(0);" class="btn_home">';
		header += '<button type="button" class="btn_img tm_home" title="Home"><img src="./images/common2015/btn_t_home.png" alt="Home"/></button>';
		header += '</a>';
		header += '<div class="header_title"> 버스도착정보 </div>';
		header += '</div>';

		$("#header").html(header);
		$('#backKey').click(function() {
			$('#busRouteList').hide();

			if ($('#busArvlInfo').css("display") == 'none') {
				makeHeader('busArvl');
				$('#busArvlInfo').show();
			}
		});

		$('#topHome').click(function() {
			location.href = "./index.bms";
		});
	} else if (type == 'routeList') {
//		header += '<div id="backKey" class="topBack"> </div>';
//		header += '<span class="topTitle"> 버스도착정보 </span>';
//		header += '<div id="topHome" class="topNavi"> </div>';

		header += '<div class="tm_headerbox">';
		header += '<a id="topHome" href="javascript:void(0);"  class="logo"><img src="./images/common2015/header_logo.png"/></a>';
		header += '<a id="backKey" href="javascript:void(0);" class="btn_home">';
		header += '<button type="button" class="btn_img tm_home" title="Home"><img src="./images/common2015/btn_t_home.png" alt="Home"/></button>';
		header += '</a>';
		header += '<div class="header_title"> 버스도착정보 </div>';
		header += '</div>';

		$("#header").html(header);
		$('#backKey').click(function() {
			$('#busRouteList').hide();

			if ($('#arsIdList').css("display") == 'none') {
				makeHeader('arsId');
				$('#arsIdList').show();
			}
		});

		$('#topHome').click(function() {
			location.href = "./index.bms";
		});
	} else if (type == 'busStation') {
//		header += '<div id="backKey" class="topBack"> </div>';
//		header += '<span class="topTitle"> 버스도착정보 </span>';
//		header += '<div id="topHome" class="topNavi"> </div>';

		header += '<div class="tm_headerbox">';
		header += '<a id="topHome" href="javascript:void(0);"  class="logo"><img src="./images/common2015/header_logo.png"/></a>';
		header += '<a id="backKey" href="javascript:void(0);" class="btn_home">';
		header += '<button type="button" class="btn_img tm_home" title="Home"><img src="./images/common2015/btn_t_home.png" alt="Home"/></button>';
		header += '</a>';
		header += '<div class="header_title"> 버스도착정보 </div>';
		header += '</div>';

		$("#header").html(header);
		$('#backKey').click(function() {
			$('#busRouteList').hide();

			if ($('#arsIdList').css("display") == 'none') {
				makeHeader('arsId');
				$('#arsIdList').show();
			}
		});

		$('#topHome').click(function() {
			location.href = "./index.bms";
		});

	} else if (type == 'busUnique') {
//		header += '<div id="backKey" class="topBack"> </div>';
//		header += '<span class="topTitle"> 버스도착정보 </span>';
//		header += '<div id="topHome" class="topNavi"> </div>';

		header += '<div class="tm_headerbox">';
		header += '<a id="topHome" href="javascript:void(0);"  class="logo"><img src="./images/common2015/header_logo.png"/></a>';
		header += '<a id="backKey" href="javascript:void(0);" class="btn_home">';
		header += '<button type="button" class="btn_img tm_home" title="Home"><img src="./images/common2015/btn_t_home.png" alt="Home"/></button>';
		header += '</a>';
		header += '<div class="header_title"> 버스도착정보 </div>';
		header += '</div>';

		$("#header").html(header);
		$('#backKey').click(function() {
			$('#busRouteList').hide();

			if ($('#arsIdList').css("display") == 'none') {
				makeHeader('arsId');
				$('#busArvlInfo').show();
			}
		});

		$('#topHome').click(function() {
			location.href = "./index.bms";
		});
	}
}

function makeSearchRouteList(strSrchUTF, strSrch, headerType) {
	var req = {
		"strSrch" : strSrchUTF
	};
	jQuery
			.ajax( {
				type : 'POST',
				dataType : 'json',
				url : '/mBus/bus/getBusRouteList.bms',
				data : req,
				success : function(data) {
					if (data.error.errorCode == '0000') {
						var pageSize = getWindowSize();

						var windowWidth = pageSize[0];
						var windowHeight = pageSize[1];
						makeHeader(headerType);
						var temp = '';

						temp += '<div class="fstTab">\"' + strSrch
								+ '\" 검색 결과</div>';
						for ( var i = 0; i < data.resultList.length; i++) { //심야21A ~ 20231204
							if(data.resultList[i].busRouteId==101000005){
								data.resultList[i].busRouteNm = '심야A21(자율주행)(토,일 미운행)';
							}
						}

						if (data.resultList != null) {
							if (data.resultList.length == 1) {
									makeRouteList(data.resultList[0].busRouteId , 'arsId');
							} else {
								var airYn, redYn, blueYn, greenYn, yellowYn, iBusYn, gBusYn, vilBusYn, tourYn, hanriverYn = false;

								for ( var i = 0; i < data.resultList.length; i++) {
									if (data.resultList[i].routeType == 1) {
										airYn = true;
									} else if (data.resultList[i].routeType == 2) {
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
										tourYn = true;
									} else if (data.resultList[i].routeType == 14) {
										hanriverYn = true;
									}
								}

								if (blueYn) {
									temp += '<div class="blueBus"> <div class="txtA"> <img src="./images/bus/blueicon.png" alt="간선버스" class="busIcon"> <span class="busAlingTxt"> 간선버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 3) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/bluebus.png" alt="간선버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (greenYn) {
									temp += '<div class="greenBus"> <div class="txtA"> <img src="./images/bus/greenicon.png" alt="지선버스" class="busIcon"> <span class="busAlingTxt"> 지선버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 4) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/greenbus.png" alt="지선버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (yellowYn) {
									temp += '<div class="yellowBus"> <div class="txtA"> <img src="./images/bus/yellowicon.png" alt="순환버스" class="busIcon"> <span class="busAlingTxt"> 순환버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 5) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/yellowbus.png" alt="순환버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (vilBusYn) {
									temp += '<div class="yellowBus"> <div class="txtA"> <img src="./images/bus/greenicon.png" alt="마을버스" class="busIcon"> <span class="busAlingTxt"> 마을버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 2) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/greenbus.png" alt="마을버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (redYn) {
									temp += '<div class="redBus"> <div class="txtA"> <img src="./images/bus/redicon.png" alt="광역버스" class="busIcon"> <span class="busAlingTxt"> 광역버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 6) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/redbus.png" alt="광역버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (airYn) {
									temp += '<div class="redBus"> <div class="txtA"> <img src="./images/bus/redicon.png" alt="공항버스" class="busIcon"> <span class="busAlingTxt"> 공항버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 1) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/redbus.png" alt="공항버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (iBusYn) {
									temp += '<div class="redBus"> <div class="txtA"> <img src="./images/bus/redicon.png" alt="인천버스" class="busIcon"> <span class="busAlingTxt"> 인천버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 7) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/ibus.png" alt="인천버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (gBusYn) {
									temp += '<div class="redBus"> <div class="txtA"> <img src="./images/bus/redicon.png" alt="경기버스" class="busIcon"> <span class="busAlingTxt"> 경기버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 8) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/gbus.png" alt="경기버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (tourYn) {
									temp += '<div class="redBus"> <div class="txtA"> <img src="./images/bus/redicon.png" alt="관광버스" class="busIcon"> <span class="busAlingTxt"> 관광버스 </span> </div> </div>';

									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 10) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/gbus.png" alt="관광버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}

								if (hanriverYn) {
									temp += '<div class="blueBus"> <div class="txtA"> <img src="./images/bus/hanrivericon.png" style="width:18px" alt="한강버스" class="busIcon"> <span class="busAlingTxt"> 한강버스 </span> </div> </div>';


									for ( var i = 0; i < data.resultList.length; i++) {
										if (data.resultList[i].routeType == 14) {
											temp += '<div class="busStationList">';
											temp += '<div class="stationNm">';
											temp += '<div style="float:left;" onclick="makeRouteList(\''
													+ data.resultList[i].busRouteId
													+ '\' , \'routeList\')">';
											temp += '<img src="./images/bus/'+  (data.resultList[i].busRouteNm.includes("급") ? "orangebus" : "bluebus" ) + '.png" alt="한강버스" class="busMark">';
											temp += '<span class="busNumvAling">'
													+ data.resultList[i].busRouteNm
													+ '</span>';
											temp += '</div>';
											temp += '<div style="float:right;"> <img src="./images/bus/favorite.png" alt="즐겨찾기" class="routeBookMark" onclick="setBookMark(\''
													+ data.resultList[i].busRouteId
													+ '\' , \''
													+ data.resultList[i].busRouteNm
													+ '\' , \'\' , \'ROUTENM\')"> </div>';
											temp += '</div>';
											temp += '</div>';
										}
									}
								}
							}
						} else {

							temp += '<div class="noResult"> 검색결과가 없습니다. </div>';
						}
						$("#arsIdList").html(temp);

					} else {
						alert(data.error.errorMessage);
					}
				},
				error : function() {
					alert("네트워크가 불안정합니다. 다시 시도해 주시기 바랍니다.");
				}
			});
}

function makeSearchFirstLetterList(stSrch, headerType) {
	var req = {
		"stSrch" : stSrch
	};
	jQuery
			.ajax( {
				type : 'POST',
				dataType : 'json',
				url : '/mBus/bus/getStationByFirstLetter.bms',
				data : req,
				success : function(data) {
					if (data.error.errorCode == '0000') {
						makeHeader(headerType);

						var temp = '';

						temp += '<div class="fstTab">\"' + stSrch
								+ '\" 검색 결과</div>';
						if (data.busList2 != null){
							temp += '<div class="redBus"><div class="txtA" style="display: flex;"> <img src="./images/bus/station.png" alt="버스정류장" style="width:26px;height:26px;" class="busIcon"> <span class="busAlingTxt"> 버스정류장 </span> </div> </div>';
							temp += '<div class="busStationList">';
							for ( var i = 0; i < data.busList2.length; i++) {
								if (data.busList2[i].arsId != 0) {
									temp += '<div class="stationNm" onclick="makeBusArvlInfo(\''
											+ data.busList2[i].arsId
											+ '\' , \'busArvl\')">';
									temp += data.busList2[i].stNm + '['
											+ data.busList2[i].arsId + ']';
									temp += '</div>';
								}
							}
							temp += '</div>';
						} else {
							temp += '<div class="noResult"> 검색결과가 없습니다. </div>';
						}

						$("#arsIdList").html(temp);

						$("#ajaxBox").hide();
//						Element.hide(ajaxBox);

					} else {
						alert(data.error.errorMessage);
					}
				},
				error : function() {
					alert("네트워크가 불안정합니다. 다시 시도해 주시기 바랍니다.");
				}
			});
}

function makeSearchNameList(stSrch, headerType) {
	var req = {
		"stSrch" : stSrch
	};
	jQuery
			.ajax( {
				type : 'POST',
				dataType : 'json',
				url : '/mBus/bus/getSearchByName.bms',
				data : req,
				success : function(data) {
					if (data.error.errorCode == '0000') {
						makeHeader(headerType);

						var temp = '';

						temp += '<div class="fstTab">\"' + stSrch
								+ '\" 검색 결과</div>';
						if (data.busList != null) {
							temp += '<div class="blueBus"> <div class="txtA" style="display: flex;"> <img src="./images/bus/station.png" alt="버스정류장" style="width:26px;height:26px;" class="busIcon"> <span class="busAlingTxt" style="font-weight: 500;"> 버스정류장 </span> </div> </div>';
							temp += '<div class="busStationList">';
							for ( var i = 0; i < data.busList.length; i++) {
								if (data.busList[i].arsId != 0) {
									temp += '<div class="stationNm" onclick="makeBusArvlInfo(\''
											+ data.busList[i].arsId
											+ '\' , \'busArvl\')">';
									temp += data.busList[i].stNm + '['
											+ data.busList[i].arsId + ']';
									temp += '</div>';
								}
							}
							temp += '</div>';
						} else {
							temp += '<div class="noResult"> 검색결과가 없습니다. </div>';
						}

						$("#arsIdList").html(temp);

					} else {
						alert(data.error.errorMessage);
					}
				},
				error : function() {
					alert("네트워크가 불안정합니다. 다시 시도해 주시기 바랍니다.");
				}
			});
}
