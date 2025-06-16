import cv2
import pyautogui
import numpy as np
import pytesseract
import pyautogui
from thefuzz import fuzz


def scaleMouse(img, textX, textY):
    sHeight, sWidth = img.shape
    print("sWidth, sHeight", sHeight, sWidth)
    width, height = pyautogui.size()
    print("width, height", width, height)
    print(textX, textY)
    scaleW, scaleY = width / sWidth, height / sHeight
    print(scaleW, scaleY)
    textX, textY = round(textX * scaleW, 2), round(textY * scaleY, 2)
    print(textX, textY)
    return textX, textY


def groupData(wordDataList):
    bestData = [0, 0, 0, 0, 0]
    combinedData = []
    i = 0
    same = False
    try:
        if len(wordDataList) > 1:
            for i in range(1, len(wordDataList)):
                if (wordDataList[i][0] != wordDataList[i - 1][0]) or (
                    wordDataList[i][1] != wordDataList[i - 1][1]
                ):
                    break
                wordDataList[0][0] = int(wordDataList[0][0])
                wordDataList[0][1] = int(wordDataList[0][1])
                wordDataList[0][2] = int(wordDataList[0][2])
                wordDataList[0][3] = int(wordDataList[0][3])
                return wordDataList[0]

            for wordData in wordDataList:
                temp = [wordData]

                for wrdData in wordDataList:
                    if wordData == wrdData:
                        continue

                    x_center_diff = abs(
                        (int(wordData[0]) + int(wordData[2]) // 2) - int(wrdData[0])
                    )
                    y_center_diff = abs(
                        (int(wordData[1]) + int(wordData[3]) // 2) - int(wrdData[1])
                    )

                    if x_center_diff < 80 and y_center_diff < 80 or same:
                        temp.append(wrdData)

                if len(temp) > 1:
                    combinedData.append(temp)

            for reference in combinedData[0]:
                i += 1
                bestData[0] += float(reference[0])
                bestData[1] += float(reference[1])
                bestData[2] += float(reference[2])
                bestData[3] += float(reference[3])
                bestData[4] += float(reference[4])

            bestData[0] = round(bestData[0] / i, 2)
            bestData[1] = round(bestData[1] / i, 2)
            bestData[2] = round(bestData[2] / i, 2)
            bestData[3] = round(bestData[3] / i, 2)
            bestData[4] = round(bestData[4] / i, 2)

            for groupedData in combinedData[1:]:
                tI = 0
                temp = [0, 0, 0, 0, 0]
                for reference in groupedData:
                    tI += 1
                    temp[0] += float(reference[0])
                    temp[1] += float(reference[1])
                    temp[2] += float(reference[2])
                    temp[3] += float(reference[3])
                    temp[4] += float(reference[4])

                temp[0] = round(temp[0] / tI, 2)
                temp[1] = round(temp[1] / tI, 2)
                temp[2] = round(temp[2] / tI, 2)
                temp[3] = round(temp[3] / tI, 2)
                temp[4] = round(temp[4] / tI, 2)

                if temp[4] > bestData[4]:
                    bestData = temp

        else:
            return bestData

    except Exception:
        return bestData

    return bestData


def getScreenText(path, text):
    wordDataList = []
    textX, textY = 0, 0

    words = text.split()

    img = cv2.imread(path)
    img = cv2.resize(img, None, fx=2, fy=2)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    psmList = [6, 11, 12]
    for psm in psmList:
        config = "--oem 3 --psm %d" % psm
        data = pytesseract.image_to_data(img, config=config, lang="eng")
        for line in data.split("\n"):
            line = [line.split("\t")]
            for word in words:
                if word in line[-1][-1] or fuzz.ratio(word, line[-1][-1]) > 50:
                    wordDataList.append(line[-1][6:])
                    print("True: ", fuzz.ratio(word, line[-1][-1]), word, line[-1][-1])

    bestData = groupData(wordDataList)

    textX = bestData[0] + bestData[2] / 2
    textY = bestData[1] + bestData[3] / 2

    textX, textY = scaleMouse(img, textX, textY)

    return textX, textY
